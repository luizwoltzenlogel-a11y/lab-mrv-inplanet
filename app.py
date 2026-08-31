import hashlib
import os
import smtplib
import time
import re
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd
import streamlit as st
from supabase import Client, create_client

# --- CONFIGURAÇÃO DE PÁGINA ---
st.set_page_config(page_title="Lab Master - InPlanet LMS", page_icon="🧪", layout="wide")

LOGO_URL = "https://cdn.prod.website-files.com/6a1be4c81b887a02620b0bb5/6a1ea2aab6347c3c4ae592a8_inplanet-logo.svg"
TEMPO_INATIVIDADE = 600

# --- ESTILIZAÇÃO CSS DE ALTO CONTRASTE (INPLANET THEMING) ---
st.markdown("""
    <style>
    :root {
        --inplanet-dark: #121512;
        --inplanet-card: #1A201B;
        --inplanet-green: #3A6B52;
    }
    .stApp { background-color: var(--inplanet-dark) !important; }
    .stForm {
        background-color: var(--inplanet-card) !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        border-radius: 12px !important;
        padding: 2rem !important;
    }
    div[data-testid="stTextInput"] input,
    div[data-testid="stPasswordInput"] input,
    div[data-testid="stNumberInput"] input,
    div[data-testid="stSelectbox"] > div > div,
    div[data-testid="stTextArea"] textarea,
    div[data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        color: #000000 !important;
        -webkit-text-fill-color: #000000 !important;
        border: 2px solid var(--inplanet-green) !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        text-transform: uppercase;
    }
    div[data-testid="stDateInput"] *,
    div[data-testid="stDateInput"] input {
        background-color: #FFFFFF !important;
        color: #000000 !important;
        -webkit-text-fill-color: #000000 !important;
        font-weight: 600 !important;
    }
    ul[role="listbox"], div[data-baseweb="popover"], div[data-baseweb="menu"],
    div[data-baseweb="datepicker"], div[data-baseweb="calendar"] {
        background-color: #FFFFFF !important;
    }
    ul[role="listbox"] *, div[data-baseweb="popover"] *, div[data-baseweb="menu"] * {
        color: #000000 !important;
        -webkit-text-fill-color: #000000 !important;
        font-weight: 600 !important;
    }
    .stButton > button, div[data-testid="stFormSubmitButton"] > button {
        background-color: var(--inplanet-green) !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 0.6rem 1rem !important;
    }
    .stButton > button:hover { background-color: #487F63 !important; }
    div[data-testid="stTextInput"] label, div[data-testid="stSelectbox"] label,
    div[data-testid="stNumberInput"] label, div[data-testid="stTextArea"] label,
    div[data-testid="stDateInput"] label, div[data-testid="stFileUploader"] label {
        color: #F0F5F2 !important;
        font-weight: 600 !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- CONEXÃO DEFENSIVA SUPABASE ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY")
        if not url or not key:
            st.error("⚠️ Configuração de Secrets do Supabase ausente.")
            st.stop()
        return create_client(url, key)
    except Exception as e:
        st.error(f"❌ Falha de inicialização com o Supabase: {e}")
        st.stop()

supabase: Client = init_connection()

# --- FUNÇÕES AUXILIARES E NOTIFICAÇÃO SMTP ---
def hash_senha(senha_plana):
    return hashlib.sha256(senha_plana.encode()).hexdigest()

def buscar_equipamentos_seguro():
    """Busca equipamentos tratando casos onde colunas novas ainda não foram propagadas no PostgREST."""
    try:
        res = supabase.table("equipamentos").select("*").eq("is_deleted", False).execute()
        return res.data or []
    except Exception:
        try:
            res = supabase.table("equipamentos").select("*").execute()
            return res.data or []
        except Exception as e:
            st.error(f"Erro ao acessar tabela 'equipamentos': {e}")
            return []

def obter_lista_gestores():
    try:
        res = supabase.table("destinatarios_alertas").select("email").eq("ativo", True).execute()
        emails = [r["email"] for r in res.data] if res.data else []
        if not emails:
            res_users = supabase.table("usuarios").select("email").eq("perfil", "Admin").execute()
            emails = [r["email"] for r in res_users.data] if res_users.data else []
        return emails if emails else ["suporte@inplanet.earth"]
    except Exception:
        return ["suporte@inplanet.earth"]

def enviar_notificacao_email(destinatario, assunto, mensagem_corpo):
    smtp_cfg = st.secrets.get("smtp")
    if not smtp_cfg:
        return False
    try:
        msg = MIMEMultipart()
        msg["From"] = smtp_cfg["user"]
        msg["To"] = destinatario
        msg["Subject"] = assunto
        msg.attach(MIMEText(mensagem_corpo, "plain", "utf-8"))
        with smtplib.SMTP(smtp_cfg["server"], int(smtp_cfg["port"])) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_cfg["user"], smtp_cfg["password"])
            server.send_message(msg)
        return True
    except Exception as e:
        st.error(f"❌ Falha no envio de e-mail SMTP: {e}")
        return False

def upload_pdf(file, prefixo):
    try:
        nome_arquivo = f"{prefixo}_{int(datetime.now().timestamp())}_{file.name}"
        supabase.storage.from_("certificados").upload(
            path=nome_arquivo, file=file.read(), file_options={"content-type": "application/pdf"}
        )
        return supabase.storage.from_("certificados").get_public_url(nome_arquivo)
    except Exception as e:
        st.error(f"Erro no Upload do PDF: {e}")
        return None

# --- SESSÃO E EXPIRAÇÃO POR INATIVIDADE ---
agora = time.time()
if "session_user" in st.query_params and "session_perfil" in st.query_params:
    st.session_state["autenticado"] = True
    st.session_state["user_email"] = st.query_params["session_user"]
    st.session_state["user_perfil"] = st.query_params["session_perfil"]

if st.session_state.get("autenticado", False):
    if "ultima_atividade" in st.session_state and (agora - st.session_state["ultima_atividade"]) > TEMPO_INATIVIDADE:
        st.session_state.clear()
        st.query_params.clear()
        st.warning("⚠️ Sessão expirada por inatividade. Faça login novamente.")
        st.rerun()
    st.session_state["ultima_atividade"] = agora

# --- TELA DE AUTENTICAÇÃO SSO (@inplanet.earth) ---
if not st.session_state.get("autenticado", False):
    col_l1, col_l2, col_l3 = st.columns([1, 1.2, 1])
    with col_l2:
        st.markdown(f"""
            <div style="text-align: center; margin-bottom: 1.2rem;">
                <img src="{LOGO_URL}" style="width: 220px; filter: brightness(0) invert(1);" />
            </div>
        """, unsafe_allow_html=True)
        st.markdown("<h2 style='text-align: center;'>🔐 Lab Master</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #9AABA0;'>Acesso Restrito - InPlanet LMS (@inplanet.earth)</p>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            email_input = st.text_input("E-mail Institucional")
            senha_input = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar no Sistema", use_container_width=True):
                email_clean = email_input.strip().lower()
                if not email_clean.endswith("@inplanet.earth"):
                    st.error("❌ Acesso negado: Somente e-mails corporativos do domínio @inplanet.earth são autorizados.")
                elif email_clean and senha_input:
                    res = supabase.table("usuarios").select("*").eq("email", email_clean).eq("senha", hash_senha(senha_input)).execute()
                    if res.data:
                        st.session_state.update({
                            "autenticado": True, 
                            "user_email": res.data[0]["email"], 
                            "user_perfil": res.data[0]["perfil"], 
                            "ultima_atividade": time.time()
                        })
                        st.query_params["session_user"] = res.data[0]["email"]
                        st.query_params["session_perfil"] = res.data[0]["perfil"]
                        st.rerun()
                    else:
                        st.error("❌ E-mail ou senha incorretos.")
                else:
                    st.warning("Preencha todos os campos.")
        
        with st.expander("🔑 Esqueci minha senha"):
            with st.form("reset_form"):
                email_reset = st.text_input("Informe seu e-mail corporativo para reset")
                if st.form_submit_button("Solicitar Reset", use_container_width=True):
                    if email_reset.endswith("@inplanet.earth"):
                        gestores = obter_lista_gestores()
                        assunto = f"🔐 Solicitação de Reset de Senha: {email_reset}"
                        corpo = f"O usuário '{email_reset}' solicitou o reset de senha de acesso ao Lab Master."
                        for g in gestores:
                            enviar_notificacao_email(g, assunto, corpo)
                        st.success("✅ Solicitação enviada aos administradores.")
                    else:
                        st.error("Informe um e-mail válido do domínio @inplanet.earth.")
    st.stop()

# --- NAVEGAÇÃO LATERAL ---
def selecionar_modulo(nome_modulo, pagina_inicial):
    st.session_state["modulo_ativo"] = nome_modulo
    st.session_state["pagina_ativa"] = pagina_inicial

if "modulo_ativo" not in st.session_state:
    st.session_state["modulo_ativo"] = "Hub"
if "pagina_ativa" not in st.session_state:
    st.session_state["pagina_ativa"] = "🏠 Hub Principal"

st.sidebar.markdown(f"""
    <div style="text-align: center; margin-bottom: 1rem;">
        <img src="{LOGO_URL}" style="width: 150px; filter: brightness(0) invert(1);" />
    </div>
""", unsafe_allow_html=True)

st.sidebar.divider()
st.sidebar.title("👤 Meu Perfil")
st.sidebar.write(f"**E-mail:** {st.session_state['user_email']}")
st.sidebar.write(f"**Permissão:** {st.session_state['user_perfil']}")

if st.sidebar.button("🚪 Sair do Sistema", use_container_width=True):
    st.session_state.clear()
    st.query_params.clear()
    st.rerun()

st.sidebar.divider()
perfil = st.session_state["user_perfil"]

if st.session_state["modulo_ativo"] == "Equipamentos":
    st.sidebar.markdown("### 🔬 Módulo Equipamentos")
    opcoes_menu = [
        "📌 Inventário & Status", 
        "🛡️ Modo Auditoria (ISO 17025)", 
        "🚨 Trabalho Não Conforme (7.10)", 
        "📈 Prontuário & Tendências", 
        "📅 Agendamentos & Logística"
    ]
    if perfil in ["Admin", "Tecnico"]:
        opcoes_menu.extend(["📝 Gerenciar Equipamentos", "📐 Calibrações & Qualificações", "🛠️ Manutenções & Intervenções"])
    if perfil == "Admin":
        opcoes_menu.append("👥 Gestão de Acessos")
elif st.session_state["modulo_ativo"] == "Reagentes":
    st.sidebar.markdown("### 📦 Módulo Reagentes")
    opcoes_menu = ["📦 Controle de Estoque"]
    if perfil == "Admin":
        opcoes_menu.append("👥 Gestão de Acessos")
else:
    st.sidebar.markdown("### 🏠 Visão Geral")
    opcoes_menu = ["🏠 Hub Principal"]
    if perfil == "Admin":
        opcoes_menu.append("👥 Gestão de Acessos")

if st.session_state["pagina_ativa"] not in opcoes_menu:
    st.session_state["pagina_ativa"] = opcoes_menu[0]

menu = st.sidebar.radio("Navegação", opcoes_menu, key="radio_dinamico")
st.session_state["pagina_ativa"] = menu

if st.session_state["modulo_ativo"] != "Hub":
    st.sidebar.divider()
    st.sidebar.button("⬅️ Voltar ao Hub Principal", on_click=selecionar_modulo, args=("Hub", "🏠 Hub Principal"), use_container_width=True)

user_email = st.session_state["user_email"]

if menu != "🏠 Hub Principal":
    st.title("🧪 Lab Master LMS")

# ==============================================================================
# 0. HUB PRINCIPAL
# ==============================================================================
if menu == "🏠 Hub Principal":
    st.markdown("<h1 style='text-align: center; color: #FFFFFF;'>Lab Master</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center; color: var(--inplanet-green);'>Sistema de Gestão Laboratorial ISO/IEC 17025</h3>", unsafe_allow_html=True)
    
    card_style = """
        background-color: var(--inplanet-card); 
        border: 2px solid var(--inplanet-green); 
        border-radius: 12px; 
        padding: 1.5rem; 
        text-align: center;
        height: 200px;
        display: flex; 
        flex-direction: column; 
        justify-content: center;
        align-items: center;
    """
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
            <div style="{card_style}">
                <h1 style="font-size: 2.5rem; margin-bottom: 0.5rem;">🔬</h1>
                <h4 style="color: #F0F5F2; margin-bottom: 0.5rem;">Gestão de Equipamentos</h4>
                <p style="color: #9AABA0; font-size: 0.85rem; margin-bottom: 0;">
                    Ativos, calibrações, manutenções, auditoria metrológica, qualificação IQ/OQ/PQ e logbook 7.10.
                </p>
            </div>
        """, unsafe_allow_html=True)
        st.write("")
        st.button("Acessar Equipamentos ➔", on_click=selecionar_modulo, args=("Equipamentos", "📌 Inventário & Status"), use_container_width=True, key="btn_hub_eq")

    with col2:
        st.markdown(f"""
            <div style="{card_style}">
                <h1 style="font-size: 2.5rem; margin-bottom: 0.5rem;">📦</h1>
                <h4 style="color: #F0F5F2; margin-bottom: 0.5rem;">Reagentes & Consumíveis</h4>
                <p style="color: #9AABA0; font-size: 0.85rem; margin-bottom: 0;">
                    Controle de estoque, lotes, validade, Laudos de Análise (CoA) e alertas automáticos de compra.
                </p>
            </div>
        """, unsafe_allow_html=True)
        st.write("")
        st.button("Acessar Reagentes ➔", on_click=selecionar_modulo, args=("Reagentes", "📦 Controle de Estoque"), use_container_width=True, key="btn_hub_reag")

# ==============================================================================
# 1. INVENTÁRIO & STATUS OPERACIONAL
# ==============================================================================
elif menu == "📌 Inventário & Status":
    st.header("📌 Inventário Geral e Status Operacional (Item 6.4 ISO 17025)")
    
    dados_eq = buscar_equipamentos_seguro()
    df = pd.DataFrame(dados_eq) if dados_eq else pd.DataFrame()
    
    if not df.empty:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total de Ativos", len(df))
        c2.metric("Operacionais", len(df[df["status"] == "Operacional"]))
        c3.metric("Em Calibração", len(df[df["status"] == "Em Calibração"]))
        c4.metric("Interditados / Quarentena", len(df[df["status"].isin(["Interditado / Fora de Uso", "Em Manutenção"])]))
        
        cols_exibir = [c for c in ["tag", "nome", "marca", "modelo", "serial_number", "periodicidade_meses", "status"] if c in df.columns]
        st.dataframe(df[cols_exibir], use_container_width=True)

        st.divider()
        st.subheader("🗓️ Planejamento Logístico de Envios")
        calib_res = supabase.table("calibracoes").select("equip_tag, data_venc").execute()
        if calib_res.data:
            df_calib = pd.DataFrame(calib_res.data)
            df_calib['data_venc_dt'] = pd.to_datetime(df_calib['data_venc'])
            hoje = pd.Timestamp.now().normalize()
            df_calib['dias_restantes'] = (df_calib['data_venc_dt'] - hoje).dt.days
            df_calib = df_calib.merge(df, left_on='equip_tag', right_on='tag', how='left')
            
            df_30 = df_calib[df_calib['dias_restantes'] <= 30]
            df_60 = df_calib[(df_calib['dias_restantes'] > 30) & (df_calib['dias_restantes'] <= 60)]
            df_90 = df_calib[(df_calib['dias_restantes'] > 60) & (df_calib['dias_restantes'] <= 90)]

            m1, m2, m3 = st.columns(3)
            m1.metric("🚨 Até 30 dias (Urgente)", f"{len(df_30)} eq.")
            m2.metric("⚠️ 31 a 60 dias", f"{len(df_60)} eq.")
            m3.metric("✈️ 61 a 90 dias", f"{len(df_90)} eq.")
    else:
        st.info("Nenhum equipamento cadastrado no sistema.")

# ==============================================================================
# 2. MODO AUDITORIA (ISO/IEC 17025)
# ==============================================================================
elif menu == "🛡️ Modo Auditoria (ISO 17025)":
    st.header("🛡️ Visão de Conformidade Metrológica para Auditoria")
    
    dados_eq = buscar_equipamentos_seguro()
    df_eq = pd.DataFrame(dados_eq)
    
    if not df_eq.empty:
        res_c = supabase.table("calibracoes").select("*").execute()
        df_c = pd.DataFrame(res_c.data or [])
        
        if not df_c.empty:
            df_c['data_venc_dt'] = pd.to_datetime(df_c['data_venc'])
            df_c_ult = df_c.sort_values('data_venc_dt', ascending=False).drop_duplicates('equip_tag')
            df_auditoria = df_eq.merge(df_c_ult, left_on='tag', right_on='equip_tag', how='left')
            
            df_auditoria['Aptidão Metrológica'] = df_auditoria['resultado'].apply(
                lambda x: "✅ Aprovado / Conforme" if x == "Aprovado" else ("❌ Reprovado" if x == "Reprovado" else "⏳ Pendente")
            )
            
            col_audit = ["tag", "nome", "marca", "modelo", "serial_number", "status", "Aptidão Metrológica", "data_calib", "data_venc", "certificado", "pdf_url"]
            cols_exist = [c for c in col_audit if c in df_auditoria.columns]
            
            st.dataframe(
                df_auditoria[cols_exist].rename(columns={"tag": "TAG", "nome": "Equipamento", "pdf_url": "Documento"}),
                column_config={"Documento": st.column_config.LinkColumn("Certificado PDF")},
                use_container_width=True
            )
        else:
            st.info("Nenhuma calibração cadastrada.")
    else:
        st.info("Nenhum equipamento cadastrado.")

# ==============================================================================
# 3. TRABALHO NÃO CONFORME (ITEM 7.10)
# ==============================================================================
elif menu == "🚨 Trabalho Não Conforme (7.10)":
    st.header("🚨 Controle de Trabalho Não Conforme (Item 7.10 ISO 17025)")
    st.caption("Registro e investigação de impacto retroativo sobre ensaios realizados com equipamentos que apresentaram falha ou reprovação.")
    
    try:
        res_tnc = supabase.table("trabalho_nao_conforme").select("*").order("criado_em", ascending=False).execute()
        df_tnc = pd.DataFrame(res_tnc.data or [])
        if not df_tnc.empty:
            st.dataframe(df_tnc[["equip_tag", "origem_evento", "analise_impacto_retroativa", "status", "criado_em"]], use_container_width=True)
        else:
            st.info("Nenhuma investigação de trabalho não conforme aberta no momento.")
    except Exception as e:
        st.warning(f"Tabela 'trabalho_nao_conforme' não identificada. Execute a migração SQL do item 1. Detalhes: {e}")

# ==============================================================================
# 4. PRONTUÁRIO & TENDÊNCIAS
# ==============================================================================
elif menu == "📈 Prontuário & Tendências":
    st.header("📈 Prontuário Metrológico e Análise de Tendências")
    dados_eq = buscar_equipamentos_seguro()
    
    if dados_eq:
        opcoes_eq = {f"{i['tag']} - {i['nome']}": i['tag'] for i in dados_eq}
        tag_alvo = opcoes_eq[st.selectbox("Selecione o Equipamento:", list(opcoes_eq.keys()))]
        
        c_res = supabase.table("calibracoes").select("*").eq("equip_tag", tag_alvo).execute()
        m_res = supabase.table("manutencoes").select("*").eq("equip_tag", tag_alvo).execute()
        
        df_c = pd.DataFrame(c_res.data or [])
        df_m = pd.DataFrame(m_res.data or [])
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total de Calibrações", len(df_c))
        c2.metric("Total de Manutenções", len(df_m))
        c3.metric("Reprovações Metrológicas", len(df_c[df_c["resultado"] == "Reprovado"]) if not df_c.empty and "resultado" in df_c.columns else 0)
        
        st.subheader("📜 Histórico do Ativo")
        if not df_c.empty:
            st.write("Calibrações Realizadas:")
            st.dataframe(df_c[["data_calib", "resultado", "certificado", "registrado_por"]], use_container_width=True)
    else:
        st.info("Nenhum equipamento disponível.")

# ==============================================================================
# 5. AGENDAMENTOS & LOGÍSTICA
# ==============================================================================
elif menu == "📅 Agendamentos & Logística":
    st.header("📅 Agendamentos, Paradas Programadas & Custos Logísticos")
    
    try:
        res_ag = supabase.table("agendamentos_logistica").select("*").execute()
        df_ag = pd.DataFrame(res_ag.data or [])
        if not df_ag.empty:
            st.dataframe(df_ag, use_container_width=True)
        else:
            st.info("Nenhum agendamento logístico pendente.")
    except Exception:
        st.warning("⚠️ Tabela 'agendamentos_logistica' não encontrada no banco.")

# ==============================================================================
# 6. REAGENTES E CONSUMÍVEIS (SEÇÃO 6.6)
# ==============================================================================
elif menu == "📦 Controle de Estoque":
    st.header("📦 Gestão de Reagentes, Consumíveis e Laudos CoA (Req. 6.6)")
    
    abas_reag = ["📊 Dashboard & Alertas", "📋 Catálogo de Produtos"]
    if perfil in ["Admin", "Tecnico"]:
        abas_reag.extend(["📥 Entrada de Lotes (CoA)", "🧪 Consumo / Baixa"])
        
    tabs = st.tabs(abas_reag)
    
    try:
        res_cat = supabase.table("reagentes").select("*").execute()
        df_cat = pd.DataFrame(res_cat.data or [])
        res_lotes = supabase.table("reagentes_lotes").select("*").execute()
        df_lotes = pd.DataFrame(res_lotes.data or [])
    except Exception:
        df_cat, df_lotes = pd.DataFrame(), pd.DataFrame()

    with tabs[0]:
        if not df_cat.empty and not df_lotes.empty:
            st.subheader("Situação Consolidada de Reagentes")
            st.dataframe(df_cat, use_container_width=True)
        else:
            st.info("Nenhum reagente cadastrado.")

    with tabs[1]:
        if perfil in ["Admin", "Tecnico"]:
            with st.form("form_novo_reagente"):
                cod = st.text_input("Código Interno *")
                nome_r = st.text_input("Nome do Reagente / Consumível *")
                unidade = st.selectbox("Unidade Medida", ["Unidade (Un)", "Litros (L)", "Mililitros (mL)", "Grama (g)", "Quilograma (kg)"])
                est_min = st.number_input("Estoque Mínimo de Segurança", min_value=0.0)
                
                if st.form_submit_button("Cadastrar Reagente"):
                    supabase.table("reagentes").insert({"codigo_interno": cod, "nome": nome_r, "unidade_medida": unidade, "estoque_minimo": float(est_min), "registrado_por": user_email}).execute()
                    st.success("Reagente adicionado ao catálogo!")
                    st.rerun()

# ==============================================================================
# 7. GERENCIAR EQUIPAMENTOS (ADMISSÃO ESTADO ZERO E REGEX)
# ==============================================================================
elif menu == "📝 Gerenciar Equipamentos" and perfil in ["Admin", "Tecnico"]:
    st.header("📝 Gestão de Equipamentos e Comissionamento ('Estado Zero')")
    
    dados_eq = buscar_equipamentos_seguro()
    df_eq_exist = pd.DataFrame(dados_eq)
    
    abas = ["📝 Cadastrar / Editar", "📁 Importação em Massa (CSV/Excel)"]
    if perfil == "Admin":
        abas.append("🗑️ Desativação Lógica (Soft Delete)")
    tabs = st.tabs(abas)
    
    with tabs[0]:
        with st.form("form_cad_equipamento"):
            c1, c2 = st.columns(2)
            tag = c1.text_input("Tag / Código Interno (Padrão: AAAA-NNN) *", placeholder="BALA-001")
            nome = c2.text_input("Nome do Equipamento *")
            
            marca = c1.text_input("Marca / Fabricante *")
            modelo = c2.text_input("Modelo *")
            
            serial = c1.text_input("Número de Série *")
            period = c2.number_input("Periodicidade de Calibração (Meses) *", min_value=1, value=12)
            
            status_op = st.selectbox("Status Inicial", ["Em Comissionamento", "Operacional", "Em Calibração", "Interditado / Fora de Uso"])
            
            if st.form_submit_button("Salvar Equipamento"):
                tag_formatada = tag.strip().upper()
                if not re.match(r'^[A-Z]{4}-\d{3}$', tag_formatada):
                    st.error("❌ A Tag deve seguir o padrão estrito de 4 letras, um hífen e 3 dígitos (Ex: BALA-001).")
                elif tag_formatada and nome:
                    dado = {
                        "tag": tag_formatada, 
                        "nome": nome, 
                        "marca": marca, 
                        "modelo": modelo, 
                        "serial_number": serial, 
                        "periodicidade_meses": int(period), 
                        "status": status_op,
                        "registrado_por": user_email
                    }
                    supabase.table("equipamentos").upsert(dado, on_conflict="tag").execute()
                    st.success(f"Equipamento {tag_formatada} salvo com sucesso!")
                    st.rerun()

    with tabs[1]:
        arquivo = st.file_uploader("Selecione o arquivo (.csv ou .xlsx)", type=["csv", "xlsx"])
        if arquivo and st.button("🚀 Processar Importação"):
            df_imp = pd.read_csv(arquivo) if arquivo.name.endswith(".csv") else pd.read_excel(arquivo)
            reg_validos = []
            for _, r in df_imp.iterrows():
                tag_i = str(r.get("tag", "")).strip().upper()
                if re.match(r'^[A-Z]{4}-\d{3}$', tag_i):
                    reg_validos.append({
                        "tag": tag_i, 
                        "nome": str(r.get("nome", "")),
                        "marca": str(r.get("marca", "")),
                        "modelo": str(r.get("modelo", "")),
                        "serial_number": str(r.get("serial_number", "")),
                        "periodicidade_meses": int(r.get("periodicidade_meses", 12)),
                        "status": "Em Comissionamento",
                        "registrado_por": user_email
                    })
            if reg_validos:
                supabase.table("equipamentos").upsert(reg_validos, on_conflict="tag").execute()
                st.success(f"{len(reg_validos)} equipamentos importados em Estado Zero!")
                st.rerun()

    if perfil == "Admin" and len(tabs) > 2:
        with tabs[2]:
            st.warning("A exclusão de equipamentos é estritamente lógica (Soft Delete) conforme item 6.4.13 da ISO 17025.")
            if not df_eq_exist.empty:
                tag_exc = st.selectbox("Selecione o Equipamento para Inativar:", df_eq_exist["tag"].tolist())
                if st.button("🚫 Confirmar Soft Delete") and st.checkbox("Confirmo a desativação"):
                    supabase.table("equipamentos").update({"is_deleted": True}).eq("tag", tag_exc).execute()
                    st.success("Equipamento marcado como desativado. Histórico preservado.")
                    st.rerun()

# ==============================================================================
# 8. CALIBRAÇÕES E AVALIAÇÃO METROLÓGICA (REGRA DE DECISÃO)
# ==============================================================================
elif menu == "📐 Calibrações & Qualificações" and perfil in ["Admin", "Tecnico"]:
    st.header("📐 Registro Metrológico de Calibração (ISO/IEC 17025 Sec 6.5)")
    
    dados_eq = buscar_equipamentos_seguro()
    equipamentos_dados = {i["tag"]: i for i in dados_eq} if dados_eq else {}
    tags = list(equipamentos_dados.keys())
    
    if tags:
        equip_tag = st.selectbox("Selecione o Equipamento *", tags)
        periodicidade_meses = equipamentos_dados[equip_tag].get("periodicidade_meses") or 12
        
        with st.form("form_calib", clear_on_submit=True):
            c1, c2 = st.columns(2)
            data_calib = c1.date_input("Data da Calibração Realizada", value=datetime.now().date())
            certificado = c2.text_input("Número do Certificado / Laudo *")
            
            st.markdown("##### 📏 Regra de Decisão Metrológica Automática")
            st.caption("Aprovação automática baseada no critério normativo: $|E| + U_{exp} \le EMP$")
            
            c3, c4, c5 = st.columns(3)
            erro_medido = c3.number_input("Erro Sistemático Medido (|E|)", format="%.6f")
            incerteza_exp = c4.number_input("Incerteza Expandida (U, k=2, 95.45%)", format="%.6f")
            emp_processo = c5.number_input("Erro Máximo Permitido (EMP)", format="%.6f", help="Insira 0 para ignorar limite físico.")
            
            pdf_file = st.file_uploader("Anexar Certificado de Calibração (PDF)", type=["pdf"])
            
            if st.form_submit_button("Avaliar Certificado & Salvar"):
                desvio_total = abs(erro_medido) + abs(incerteza_exp)
                is_conforme = True
                if emp_processo > 0 and desvio_total > emp_processo:
                    is_conforme = False
                    
                resultado = "Aprovado" if is_conforme else "Reprovado"
                data_venc = (pd.to_datetime(data_calib) + pd.DateOffset(months=periodicidade_meses)).date()
                pdf_url = upload_pdf(pdf_file, f"CALIB_{equip_tag}") if pdf_file else None

                supabase.table("calibracoes").insert({
                    "equip_tag": equip_tag,
                    "data_calib": str(data_calib),
                    "data_venc": str(data_venc),
                    "resultado": resultado,
                    "certificado": certificado,
                    "erro_medido": float(erro_medido),
                    "incerteza_exp": float(incerteza_exp),
                    "emp_processo": float(emp_processo),
                    "is_conforme": is_conforme,
                    "pdf_url": pdf_url,
                    "registrado_por": user_email
                }).execute()

                novo_status = "Operacional" if is_conforme else "Interditado / Fora de Uso"
                supabase.table("equipamentos").update({"status": novo_status}).eq("tag", equip_tag).execute()

                if not is_conforme:
                    supabase.table("trabalho_nao_conforme").insert({
                        "equip_tag": equip_tag,
                        "origem_evento": f"Reprovação Metrológica no Laudo {certificado}",
                        "analise_impacto_retroativa": f"INVESTIGAÇÃO AUTOMÁTICA ISO 17025 (SEÇÃO 7.10): (|E| + U = {desvio_total:.6f} > EMP {emp_processo:.6f}). Avaliar validade dos ensaios executados.",
                        "registrado_por": user_email
                    }).execute()
                    st.error(f"🚨 Calibração REPROVADA! (|E| + U = {desvio_total:.6f} > EMP {emp_processo:.6f}). Equipamento INTERDITADO.")
                else:
                    st.success(f"✅ Calibração APROVADA! (|E| + U = {desvio_total:.6f} ≤ EMP {emp_processo:.6f}). Equipamento Operacional.")
                    
                time.sleep(2)
                st.rerun()

# ==============================================================================
# 9. MANUTENÇÕES
# ==============================================================================
elif menu == "🛠️ Manutenções & Intervenções" and perfil in ["Admin", "Tecnico"]:
    st.header("🛠️ Registro de Manutenção e Intervenções Técnicas")
    dados_eq = buscar_equipamentos_seguro()
    tags = [i["tag"] for i in dados_eq] if dados_eq else []
    
    if tags:
        with st.form("form_manut"):
            c1, c2 = st.columns(2)
            equip_tag = c1.selectbox("Equipamento *", tags)
            tipo = c2.selectbox("Tipo *", ["Preventiva", "Corretiva", "Ajuste Interno"])
            data_m = c1.date_input("Data da Intervenção", value=datetime.now().date())
            tecnico = c2.text_input("Técnico / Empresa Responsável")
            status_pos = st.selectbox("Status Pós-Manutenção", ["Operacional", "Em Calibração", "Interditado / Fora de Uso"])
            desc = st.text_area("Descrição do Serviço")
            pdf_file = st.file_uploader("Relatório de Manutenção (PDF)", type=["pdf"])
            
            if st.form_submit_button("Registrar Manutenção"):
                pdf_url = upload_pdf(pdf_file, f"MANUT_{equip_tag}") if pdf_file else None
                supabase.table("manutencoes").insert({
                    "equip_tag": equip_tag, 
                    "tipo": tipo, 
                    "data_intervencao": str(data_m), 
                    "tecnico": tecnico, 
                    "descricao": desc, 
                    "pdf_url": pdf_url, 
                    "registrado_por": user_email
                }).execute()
                
                supabase.table("equipamentos").update({"status": status_pos}).eq("tag", equip_tag).execute()
                st.success("Manutenção registrada com sucesso!")
                st.rerun()

# ==============================================================================
# 10. GESTÃO DE ACESSOS E DESTINATÁRIOS DE ALERTAS
# ==============================================================================
elif menu == "👥 Gestão de Acessos" and perfil == "Admin":
    st.header("👥 Gestão de Usuários e Destinatários de Alertas")
    tab_users, tab_alertas = st.tabs(["👤 Controle de Usuários", "📩 Destinatários de Alertas"])
    
    with tab_users:
        res_u = supabase.table("usuarios").select("email, perfil, criado_em").execute()
        if res_u.data:
            st.dataframe(pd.DataFrame(res_u.data), use_container_width=True)
            
        with st.form("form_user"):
            c1, c2, c3 = st.columns(3)
            n_email = c1.text_input("E-mail corporativo (@inplanet.earth)")
            n_perfil = c2.selectbox("Perfil", ["Leitura", "Tecnico", "Admin"])
            n_senha = c3.text_input("Senha", type="password")
            
            if st.form_submit_button("Salvar Usuário"):
                if n_email.endswith("@inplanet.earth") and n_senha:
                    supabase.table("usuarios").upsert({"email": n_email, "perfil": n_perfil, "senha": hash_senha(n_senha)}, on_conflict="email").execute()
                    st.success("Usuário registrado com sucesso!")
                    st.rerun()
                else:
                    st.error("Informe um e-mail válido do domínio @inplanet.earth.")

    with tab_alertas:
        res_dest = supabase.table("destinatarios_alertas").select("*").execute()
        if res_dest.data:
            st.dataframe(pd.DataFrame(res_dest.data), use_container_width=True)
            
        with st.form("form_dest"):
            c1, c2 = st.columns([2, 1])
            email_a = c1.text_input("E-mail do Destinatário")
            status_a = c2.selectbox("Status", [True, False], format_func=lambda x: "Ativo" if x else "Inativo")
            if st.form_submit_button("Salvar Destinatário") and email_a:
                supabase.table("destinatarios_alertas").upsert({"email": email_a, "ativo": status_a}, on_conflict="email").execute()
                st.success("Destinatário salvo!")
                st.rerun()
