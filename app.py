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

# Configuração de Página
st.set_page_config(page_title="Lab Master - InPlanet LMS", page_icon="🧪", layout="wide")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_URL = "https://cdn.prod.website-files.com/6a1be4c81b887a02620b0bb5/6a1ea2aab6347c3c4ae592a8_inplanet-logo.svg"
TEMPO_INATIVIDADE = 600

# --- RESOLUÇÃO DE CAMINHO PARA LOGO DA CAPIVARA ---
def obter_caminho_logo_capivara():
    candidatos = [
        "logo_labmaster.jpg", "logo_labmaster.jpeg", "logo_labmaster.png",
        "capivara.jpg", "capivara.png", "logo.png"
    ]
    for nome in candidatos:
        caminho = os.path.join(BASE_DIR, nome)
        if os.path.exists(caminho):
            return caminho
    return None

def renderizar_logo_capivara(largura=200):
    caminho = obter_caminho_logo_capivara()
    if caminho:
        st.image(caminho, width=largura)
    else:
        st.markdown("<h2 style='text-align: center; color: #3A6B52;'>🧪 Lab Master</h2>", unsafe_allow_html=True)

# --- CSS DE ALTO CONTRASTE (INPLANET DESIGN SYSTEM) ---
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

# --- CONEXÃO PROTEGIDA SUPABASE ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY")
        if not url or not key:
            st.error("⚠️ Configuração de Secrets 'SUPABASE_URL' ou 'SUPABASE_KEY' ausente.")
            st.stop()
        return create_client(url, key)
    except Exception as e:
        st.error(f"❌ Erro ao conectar com Supabase: {e}")
        st.stop()

supabase: Client = init_connection()

# --- FUNÇÕES DE SEGURANÇA E E-MAIL ---
def hash_senha(senha_plana):
    return hashlib.sha256(senha_plana.encode()).hexdigest()

def buscar_equipamentos_seguro():
    try:
        res = supabase.table("equipamentos").select("*").eq("is_deleted", False).execute()
        return res.data or []
    except Exception:
        try:
            res = supabase.table("equipamentos").select("*").execute()
            return res.data or []
        except Exception as e:
            st.error(f"Erro ao acessar equipamentos: {e}")
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
        st.error(f"❌ Falha no envio de e-mail: {e}")
        return False

def upload_pdf(file, prefixo):
    try:
        nome_arquivo = f"{prefixo}_{int(datetime.now().timestamp())}_{file.name}"
        supabase.storage.from_("certificados").upload(
            path=nome_arquivo, file=file.read(), file_options={"content-type": "application/pdf"}
        )
        return supabase.storage.from_("certificados").get_public_url(nome_arquivo)
    except Exception as e:
        st.error(f"Erro no upload do PDF: {e}")
        return None

# --- GERENCIAMENTO DE SESSÃO E TIMEOUT ---
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

# ==============================================================================
# TELA DE LOGIN (CENTRALIZADA)
# ==============================================================================
if not st.session_state.get("autenticado", False):
    col_l1, col_l2, col_l3 = st.columns([1, 1.2, 1])
    with col_l2:
        col_img1, col_img2, col_img3 = st.columns([1, 2, 1])
        with col_img2:
            renderizar_logo_capivara(largura=220)
        
        st.markdown("<p style='text-align: center; color: #9AABA0; margin-top: 0.5rem; margin-bottom: 1.5rem;'>Acesso Restrito - @inplanet.earth</p>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            email_input = st.text_input("E-mail Institucional")
            senha_input = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar no Sistema", use_container_width=True):
                email_clean = email_input.strip().lower()
                if not email_clean.endswith("@inplanet.earth"):
                    st.error("❌ Somente e-mails corporativos do domínio @inplanet.earth são autorizados.")
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
                email_reset = st.text_input("E-mail Institucional para reset")
                if st.form_submit_button("Solicitar Reset de Senha", use_container_width=True):
                    if email_reset.endswith("@inplanet.earth"):
                        gestores = obter_lista_gestores()
                        assunto = f"🔐 Solicitação de Reset de Senha: {email_reset}"
                        corpo = f"Atenção Administrador,\n\nO usuário '{email_reset}' solicitou o reset de senha de acesso ao Lab Master."
                        for g in gestores:
                            enviar_notificacao_email(g, assunto, corpo)
                        st.success("✅ Solicitação enviada aos administradores!")
                    else:
                        st.error("Informe um e-mail válido @inplanet.earth.")
    st.stop()

# ==============================================================================
# BARRA LATERAL
# ==============================================================================
def selecionar_modulo(nome_modulo, pagina_inicial):
    st.session_state["modulo_ativo"] = nome_modulo
    st.session_state["pagina_ativa"] = pagina_inicial

if "modulo_ativo" not in st.session_state:
    st.session_state["modulo_ativo"] = "Hub"
if "pagina_ativa" not in st.session_state:
    st.session_state["pagina_ativa"] = "🏠 Hub Principal"

st.sidebar.markdown(f"""
    <div style="text-align: center; margin-bottom: 1rem;">
        <img src="{LOGO_URL}" style="width: 160px; filter: brightness(0) invert(1);" />
    </div>
""", unsafe_allow_html=True)

st.sidebar.divider()
st.sidebar.title("👤 Meu Perfil")
st.sidebar.write(f"**E-mail:** {st.session_state['user_email']}")
st.sidebar.write(f"**Permissão:** {st.session_state['user_perfil']}")

with st.sidebar.expander("🔑 Alterar Senha"):
    with st.form("form_change_pwd", clear_on_submit=True):
        senha_atual = st.text_input("Senha Atual", type="password")
        nova_senha = st.text_input("Nova Senha", type="password")
        confirma_senha = st.text_input("Confirmar Nova Senha", type="password")
        
        if st.form_submit_button("Atualizar Senha", use_container_width=True):
            if not senha_atual or not nova_senha or not confirma_senha:
                st.error("Preencha todos os campos.")
            elif nova_senha != confirma_senha:
                st.error("A nova senha e a confirmação não coincidem.")
            else:
                user_email = st.session_state["user_email"]
                res_val = supabase.table("usuarios").select("id").eq("email", user_email).eq("senha", hash_senha(senha_atual)).execute()
                if res_val.data:
                    supabase.table("usuarios").update({"senha": hash_senha(nova_senha)}).eq("email", user_email).execute()
                    st.success("✅ Senha atualizada com sucesso!")
                else:
                    st.error("❌ A Senha Atual está incorreta.")

st.sidebar.write("")
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
    col_lh1, col_lh2, col_lh3 = st.columns([1, 1.5, 1])
    with col_lh2:
        renderizar_logo_capivara(largura=320)
        
    st.markdown("<h3 style='text-align: center; color: var(--inplanet-green); margin-top: 0px;'>Sistema de Gestão Laboratorial ISO/IEC 17025</h3>", unsafe_allow_html=True)
    st.write("")
    
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
                    Ativos, rastreabilidade metrológica, calibrações, logbook de ocorrências e seção 7.10.
                </p>
            </div>
        """, unsafe_allow_html=True)
        st.write("")
        st.button("Acessar Módulo de Equipamentos ➔", on_click=selecionar_modulo, args=("Equipamentos", "📌 Inventário & Status"), use_container_width=True, key="btn_hub_eq")

    with col2:
        st.markdown(f"""
            <div style="{card_style}">
                <h1 style="font-size: 2.5rem; margin-bottom: 0.5rem;">📦</h1>
                <h4 style="color: #F0F5F2; margin-bottom: 0.5rem;">Reagentes & Consumíveis</h4>
                <p style="color: #9AABA0; font-size: 0.85rem; margin-bottom: 0;">
                    Controle de frascos, lotes, validade, Laudos de Análise (CoA) e alertas de estoque crítico.
                </p>
            </div>
        """, unsafe_allow_html=True)
        st.write("")
        st.button("Acessar Módulo de Reagentes & Consumíveis ➔", on_click=selecionar_modulo, args=("Reagentes", "📦 Controle de Estoque"), use_container_width=True, key="btn_hub_reag")

# ==============================================================================
# 1. EQUIPAMENTOS - INVENTÁRIO
# ==============================================================================
elif menu == "📌 Inventário & Status":
    st.header("📌 Inventário Geral e Status Operacional")
    dados_eq = buscar_equipamentos_seguro()
    df = pd.DataFrame(dados_eq) if dados_eq else pd.DataFrame()
    
    if not df.empty:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", len(df))
        c2.metric("Operacionais", len(df[df["status"] == "Operacional"]))
        c3.metric("Em Calibração", len(df[df["status"] == "Em Calibração"]))
        c4.metric("Interditados/Manutenção", len(df[df["status"].isin(["Interditado / Fora de Uso", "Em Manutenção"])]))
        
        cols_exibir = [c for c in ["tag", "nome", "marca", "modelo", "serial_number", "periodicidade_meses", "status", "modalidade_calibracao"] if c in df.columns]
        st.dataframe(df[cols_exibir], use_container_width=True)

        st.divider()
        st.subheader("🗓️ Planejamento Logístico de Envio (30, 60 e 90 dias)")
        
        calib_res = supabase.table("calibracoes").select("equip_tag, data_venc").execute()
        if calib_res.data:
            df_calib = pd.DataFrame(calib_res.data)
            df_calib['data_venc_dt'] = pd.to_datetime(df_calib['data_venc'])
            hoje = pd.Timestamp.now().normalize()
            
            df_calib = df_calib.sort_values('data_venc_dt', ascending=False).drop_duplicates('equip_tag')
            df_calib['dias_restantes'] = (df_calib['data_venc_dt'] - hoje).dt.days
            df_calib = df_calib.merge(df, left_on='equip_tag', right_on='tag', how='left')
            
            df_30 = df_calib[df_calib['dias_restantes'] <= 30].sort_values('dias_restantes')
            df_60 = df_calib[(df_calib['dias_restantes'] > 30) & (df_calib['dias_restantes'] <= 60)].sort_values('dias_restantes')
            df_90 = df_calib[(df_calib['dias_restantes'] > 60) & (df_calib['dias_restantes'] <= 90)].sort_values('dias_restantes')

            m1, m2, m3 = st.columns(3)
            m1.metric("🚨 Urgente (Até 30 dias)", f"{len(df_30)} eq.")
            m2.metric("⚠️ Médio Prazo (31-60 dias)", f"{len(df_60)} eq.")
            m3.metric("✈️ Longo Prazo (61-90 dias)", f"{len(df_90)} eq.")

            t30, t60, t90 = st.tabs(["🔴 Até 30 dias", "🟡 31 a 60 dias", "🔵 61 a 90 dias"])
            cols_v = [c for c in ['equip_tag', 'nome', 'marca', 'modalidade_calibracao', 'data_venc', 'dias_restantes', 'status'] if c in df_calib.columns]

            with t30: st.dataframe(df_30[cols_v] if not df_30.empty else pd.DataFrame(), use_container_width=True)
            with t60: st.dataframe(df_60[cols_v] if not df_60.empty else pd.DataFrame(), use_container_width=True)
            with t90: st.dataframe(df_90[cols_v] if not df_90.empty else pd.DataFrame(), use_container_width=True)
    else:
        st.info("Nenhum equipamento cadastrado.")

# ==============================================================================
# 2. MODO AUDITORIA (ISO 17025)
# ==============================================================================
elif menu == "🛡️ Modo Auditoria (ISO 17025)":
    st.header("🛡️ Visão de Conformidade Metrológica - Auditoria")
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
            
            df_final = df_auditoria[cols_exist].rename(columns={
                'tag': 'TAG', 'nome': 'Equipamento', 'marca': 'Marca', 'modelo': 'Modelo',
                'serial_number': 'Nº Série', 'status': 'Status Atual', 'data_calib': 'Última Calibração',
                'data_venc': 'Vencimento', 'certificado': 'Certificado nº', 'pdf_url': 'Documento'
            })
            
            st.dataframe(
                df_final, 
                column_config={"Documento": st.column_config.LinkColumn("Certificado PDF")}, 
                use_container_width=True
            )
        else:
            st.info("Nenhuma calibração cadastrada.")
    else:
        st.info("Nenhum equipamento cadastrado.")

# ==============================================================================
# 3. TRABALHO NÃO CONFORME (SEÇÃO 7.10)
# ==============================================================================
elif menu == "🚨 Trabalho Não Conforme (7.10)":
    st.header("🚨 Gestão de Trabalho Não Conforme (Item 7.10 ISO 17025)")
    st.caption("Requisito normativo para interrupção de trabalhos e análise retroativa do impacto de falhas sobre ensaios efetuados.")
    
    try:
        res_tnc = supabase.table("trabalho_nao_conforme").select("*").order("criado_em", ascending=False).execute()
        df_tnc = pd.DataFrame(res_tnc.data or [])
        if not df_tnc.empty:
            st.dataframe(df_tnc[["equip_tag", "origem_evento", "analise_impacto_retroativa", "status", "criado_em"]], use_container_width=True)
        else:
            st.info("Nenhuma investigação de trabalho não conforme aberta no momento.")
    except Exception as e:
        st.warning(f"Tabela de trabalho não conforme pendente de inicialização: {e}")

# ==============================================================================
# 4. PRONTUÁRIO & TENDÊNCIAS
# ==============================================================================
elif menu == "📈 Prontuário & Tendências":
    st.header("📈 Prontuário do Equipamento e Análise de Tendências")
    dados_eq = buscar_equipamentos_seguro()
    
    if dados_eq:
        opcoes_eq = {f"{i['tag']} - {i['nome']}": i['tag'] for i in dados_eq}
        tag_alvo = opcoes_eq[st.selectbox("Selecione o equipamento para análise detalhada:", list(opcoes_eq.keys()))]
        
        c_res = supabase.table("calibracoes").select("*").eq("equip_tag", tag_alvo).execute()
        m_res = supabase.table("manutencoes").select("*").eq("equip_tag", tag_alvo).execute()
        
        df_c = pd.DataFrame(c_res.data or [])
        df_m = pd.DataFrame(m_res.data or [])
        
        tot_corretivas = len(df_m[df_m["tipo"] == "Corretiva"]) if not df_m.empty and "tipo" in df_m.columns else 0
        tot_preventivas = len(df_m[df_m["tipo"] == "Preventiva"]) if not df_m.empty and "tipo" in df_m.columns else 0
        tot_reprovacoes = len(df_c[df_c["resultado"] == "Reprovado"]) if not df_c.empty and "resultado" in df_c.columns else 0
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Manutenções Corretivas", tot_corretivas)
        col2.metric("Manutenções Preventivas", tot_preventivas)
        col3.metric("Reprovações em Calibração", tot_reprovacoes)
        col4.metric("Total de Registros", len(df_c) + len(df_m))
        
        if not df_c.empty:
            st.subheader("📜 Histórico de Calibrações")
            st.dataframe(df_c[["data_calib", "resultado", "certificado", "registrado_por"]], use_container_width=True)
    else:
        st.info("Nenhum equipamento cadastrado.")

# ==============================================================================
# 5. AGENDAMENTOS & LOGÍSTICA
# ==============================================================================
elif menu == "📅 Agendamentos & Logística":
    st.header("📅 Agendamentos, Paradas Programadas & Logística")
    
    abas_ag = ["🗓️ Cronograma & Paradas", "📊 Custos Logísticos"]
    if perfil in ["Admin", "Tecnico"]:
        abas_ag.insert(1, "➕ Intervenção Manual / Fora de Prazo")
        
    tabs = st.tabs(abas_ag)
    
    try:
        res_ag = supabase.table("agendamentos_logistica").select("*").execute()
        df_ag = pd.DataFrame(res_ag.data or [])
    except Exception:
        df_ag = pd.DataFrame()

    with tabs[0]:
        if not df_ag.empty:
            st.dataframe(df_ag, use_container_width=True)
        else:
            st.info("Nenhum agendamento logístico registrado.")

# ==============================================================================
# 6. REAGENTES E CONSUMÍVEIS
# ==============================================================================
elif menu == "📦 Controle de Estoque":
    st.header("📦 Gestão de Reagentes e Consumíveis (Req. 6.6)")
    
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
            st.subheader("Estoque Geral Consolidado")
            st.dataframe(df_cat, use_container_width=True)
        else:
            st.info("Nenhum produto cadastrado no estoque.")

    with tabs[1]:
        if perfil in ["Admin", "Tecnico"]:
            st.subheader("Cadastrar Produto no Catálogo")
            with st.form("form_cat_prod", clear_on_submit=True):
                col1, col2 = st.columns(2)
                cod_in = col1.text_input("Código Interno *", placeholder="REAG-001")
                nome_p = col1.text_input("Nome do Produto *")
                cas_p = col2.text_input("CAS Number / Part Number")
                unid_p = col2.selectbox("Unidade de Medida", ["Unidade (Un)", "Caixa (Cx)", "Litros (L)", "Mililitros (mL)", "Grama (g)", "Quilograma (kg)"])
                est_min = col1.number_input("Estoque Mínimo de Segurança", min_value=0.0)
                
                if st.form_submit_button("Salvar Produto"):
                    if cod_in and nome_p:
                        supabase.table("reagentes").insert({
                            "codigo_interno": cod_in, "nome": nome_p, "cas_number": cas_p,
                            "unidade_medida": unid_p, "estoque_minimo": float(est_min),
                            "registrado_por": user_email
                        }).execute()
                        st.success(f"Produto {nome_p} cadastrado com sucesso!")
                        st.rerun()

# ==============================================================================
# 7. GERENCIAR EQUIPAMENTOS
# ==============================================================================
elif menu == "📝 Gerenciar Equipamentos" and perfil in ["Admin", "Tecnico"]:
    st.header("📝 Gestão de Equipamentos (Req. 6.4.13)")
    dados_eq = buscar_equipamentos_seguro()
    df_eq_exist = pd.DataFrame(dados_eq)
    
    abas = ["📝 Cadastrar / Editar", "📁 Importação em Massa"]
    if perfil == "Admin": abas.append("🗑️ Excluir Lógica (Soft Delete)")
    tabs = st.tabs(abas)
    
    with tabs[0]:
        with st.form("form_equip_cadastro"):
            c1, c2 = st.columns(2)
            tag = c1.text_input("Tag / Código Interno *", placeholder="Ex: BALA-001", help="Padrão obrigatório: 4 letras, hífen e 3 números")
            nome = c2.text_input("Nome do Equipamento *")
            marca = c1.text_input("Marca / Fabricante")
            modelo = c2.text_input("Modelo")
            serial = c1.text_input("Número de Série")
            period = c2.number_input("Periodicidade de Calibração (Meses)", min_value=1, value=12)
            
            if st.form_submit_button("Salvar Equipamento"):
                tag_clean = tag.strip().upper()
                if not re.match(r'^[A-Z]{4}-\d{3}$', tag_clean):
                    st.error("❌ A Tag deve seguir estritamente o padrão de 4 letras, um hífen e 3 números (Ex: BALA-001).")
                elif tag_clean and nome:
                    supabase.table("equipamentos").upsert({
                        "tag": tag_clean, "nome": nome, "marca": marca, "modelo": modelo,
                        "serial_number": serial, "periodicidade_meses": int(period),
                        "status": "Em Comissionamento", "registrado_por": user_email
                    }, on_conflict="tag").execute()
                    st.success(f"Equipamento {tag_clean} gravado com sucesso!")
                    st.rerun()

    if perfil == "Admin" and len(tabs) > 2:
        with tabs[2]:
            st.warning("Soft Delete: O equipamento será marcado como inativo e preservará o histórico imutável.")
            if not df_eq_exist.empty:
                tag_exc = st.selectbox("Selecione a TAG:", df_eq_exist["tag"].tolist())
                if st.button("🗑️ Confirmar Desativação Lógica") and st.checkbox("Confirmo a exclusão lógica"):
                    supabase.table("equipamentos").update({"is_deleted": True}).eq("tag", tag_exc).execute()
                    st.success("Equipamento desativado com sucesso!")
                    st.rerun()

# ==============================================================================
# 8. CALIBRAÇÕES E REGRA DE DECISÃO METROLÓGICA (|E| + U <= EMP)
# ==============================================================================
elif menu == "📐 Calibrações & Qualificações" and perfil in ["Admin", "Tecnico"]:
    st.header("📐 Registro Metrológico de Calibração (ISO 17025 Sec 6.5)")
    dados_eq = buscar_equipamentos_seguro()
    equipamentos_dados = {i["tag"]: i for i in dados_eq} if dados_eq else {}
    tags = list(equipamentos_dados.keys())
    
    if tags:
        equip_tag = st.selectbox("Selecione o Equipamento *", tags)
        periodicidade_meses = equipamentos_dados[equip_tag].get("periodicidade_meses") or 12
        
        with st.form("form_calib_metro", clear_on_submit=True):
            c1, c2 = st.columns(2)
            data_calib = c1.date_input("Data da Calibração", value=datetime.now().date())
            certificado = c2.text_input("Número do Certificado / Laudo *")
            
            st.markdown("##### 📏 Avaliação Metrológica Automática")
            c3, c4, c5 = st.columns(3)
            erro_medido = c3.number_input("Erro Sistemático Medido (|E|)", format="%.6f")
            incerteza_exp = c4.number_input("Incerteza Expandida (U, k=2)", format="%.6f")
            emp_processo = c5.number_input("Erro Máximo Permitido (EMP)", format="%.6f")
            
            pdf_file = st.file_uploader("Anexar Certificado (PDF)", type=["pdf"])
            
            if st.form_submit_button("Avaliar Certificado & Salvar"):
                desvio_total = abs(erro_medido) + abs(incerteza_exp)
                is_conforme = True
                if emp_processo > 0 and desvio_total > emp_processo:
                    is_conforme = False

                resultado = "Aprovado" if is_conforme else "Reprovado"
                data_venc = (pd.to_datetime(data_calib) + pd.DateOffset(months=periodicidade_meses)).date()
                pdf_url = upload_pdf(pdf_file, f"CALIB_{equip_tag}") if pdf_file else None

                supabase.table("calibracoes").insert({
                    "equip_tag": equip_tag, "data_calib": str(data_calib),
                    "data_venc": str(data_venc), "resultado": resultado,
                    "certificado": certificado, "erro_medido": float(erro_medido),
                    "incerteza_exp": float(incerteza_exp), "emp_processo": float(emp_processo),
                    "is_conforme": is_conforme, "pdf_url": pdf_url, "registrado_por": user_email
                }).execute()

                novo_status = "Operacional" if is_conforme else "Interditado / Fora de Uso"
                supabase.table("equipamentos").update({"status": novo_status}).eq("tag", equip_tag).execute()

                if is_conforme:
                    st.success(f"✅ Calibração APROVADA! (|E| + U = {desvio_total:.6f} ≤ EMP {emp_processo:.6f}). Equipamento Operacional.")
                else:
                    st.error(f"🚨 Calibração REPROVADA! (|E| + U = {desvio_total:.6f} > EMP {emp_processo:.6f}). Equipamento INTERDITADO e enviado para Seção 7.10.")
                
                time.sleep(2)
                st.rerun()

# ==============================================================================
# 9. MANUTENÇÕES
# ==============================================================================
elif menu == "🛠️ Manutenções & Intervenções" and perfil in ["Admin", "Tecnico"]:
    st.header("🛠️ Registro de Manutenção")
    dados_eq = buscar_equipamentos_seguro()
    tags = [i["tag"] for i in dados_eq] if dados_eq else []
    
    if tags:
        with st.form("form_manut"):
            c1, c2 = st.columns(2)
            equip_tag = c1.selectbox("Equipamento *", tags)
            tipo = c2.selectbox("Tipo de Intervenção", ["Preventiva", "Corretiva", "Ajuste / Qualificação"])
            data_m = c1.date_input("Data da Intervenção")
            tecnico = c2.text_input("Técnico / Empresa Responsável")
            status_pos = st.selectbox("Status Pós-Manutenção", ["Operacional", "Em Calibração", "Interditado / Fora de Uso"])
            desc = st.text_area("Descrição Detalhada")
            pdf_file = st.file_uploader("Relatório em PDF", type=["pdf"])
            
            if st.form_submit_button("Salvar Manutenção"):
                pdf_url = upload_pdf(pdf_file, f"MANUT_{equip_tag}") if pdf_file else None
                supabase.table("manutencoes").insert({
                    "equip_tag": equip_tag, "tipo": tipo, "data_intervencao": str(data_m),
                    "tecnico": tecnico, "descricao": desc, "pdf_url": pdf_url, "registrado_por": user_email
                }).execute()
                supabase.table("equipamentos").update({"status": status_pos}).eq("tag", equip_tag).execute()
                st.success("Manutenção registrada!")
                st.rerun()

# ==============================================================================
# 10. GESTÃO DE ACESSOS E DESTINATÁRIOS DE ALERTAS
# ==============================================================================
elif menu == "👥 Gestão de Acessos" and perfil == "Admin":
    st.header("👥 Gestão de Usuários e Destinatários de Alertas")
    tab_users, tab_alertas = st.tabs(["👤 Controle de Usuários", "📩 Destinatários de Alertas"])
    
    with tab_users:
        st.subheader("Usuários Cadastrados no Sistema")
        res_users = supabase.table("usuarios").select("id, email, perfil, criado_em").execute()
        if res_users.data:
            st.dataframe(pd.DataFrame(res_users.data)[["email", "perfil", "criado_em"]], use_container_width=True)
            
        st.divider()
        st.subheader("Cadastrar Novo Usuário (@inplanet.earth)")
        with st.form("form_novo_usuario", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            novo_email = col1.text_input("E-mail Corporativo (@inplanet.earth)")
            novo_perfil = col2.selectbox("Perfil de Permissão", ["Leitura", "Tecnico", "Admin"])
            nova_senha = col3.text_input("Senha de Acesso", type="password")
            
            if st.form_submit_button("Salvar Usuário"):
                if novo_email.endswith("@inplanet.earth") and nova_senha:
                    supabase.table("usuarios").upsert({
                        "email": novo_email, "perfil": novo_perfil, "senha": hash_senha(nova_senha)
                    }, on_conflict="email").execute()
                    
                    assunto = "🧪 Bem-vindo ao Lab Master - Credenciais de Acesso"
                    corpo = f"Olá!\n\nSeu usuário foi cadastrado no Lab Master LMS.\n\nE-mail: {novo_email}\nPerfil: {novo_perfil}\nSenha: {nova_senha}\n\nAcesse o sistema e altere sua senha no menu lateral."
                    enviar_notificacao_email(novo_email, assunto, corpo)
                    
                    st.success("Usuário registrado com sucesso e e-mail de boas-vindas enviado!")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("Informe um e-mail válido com o domínio @inplanet.earth e uma senha válida.")

    with tab_alertas:
        st.subheader("Destinatários de Alertas Automáticos")
        res_dest = supabase.table("destinatarios_alertas").select("*").execute()
        if res_dest.data:
            st.dataframe(pd.DataFrame(res_dest.data)[["email", "ativo", "criado_em"]], use_container_width=True)
            
        with st.form("form_destinatario", clear_on_submit=True):
            c1, c2 = st.columns([2, 1])
            email_alerta = c1.text_input("E-mail do Destinatário")
            status_alerta = c2.selectbox("Status", [True, False], format_func=lambda x: "Ativo" if x else "Inativo")
            if st.form_submit_button("Salvar Destinatário") and email_alerta:
                supabase.table("destinatarios_alertas").upsert({"email": email_alerta, "ativo": status_alerta}, on_conflict="email").execute()
                st.success("Destinatário salvo com sucesso!")
                st.rerun()
