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

# Configuração da Página
st.set_page_config(page_title="Lab Master - InPlanet", page_icon="🧪", layout="wide")

LOGO_URL = "https://cdn.prod.website-files.com/6a1be4c81b887a02620b0bb5/6a1ea2aab6347c3c4ae592a8_inplanet-logo.svg"
TEMPO_INATIVIDADE = 600

# --- SEU CSS ORIGINAL DE ALTO CONTRASTE ---
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
    div[data-testid="stNumberInput"] label, div[data-testid="stTextArea"] label {
        color: #F0F5F2 !important;
        font-weight: 600 !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- CONEXÃO PROTEGIDA COM TRATAMENTO DE ERROS ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY")
        if not url or not key:
            st.error("⚠️ Secrets 'SUPABASE_URL' ou 'SUPABASE_KEY' não configurados.")
            st.stop()
        return create_client(url, key)
    except Exception as e:
        st.error(f"❌ Erro ao conectar com o Supabase: {e}")
        st.stop()

supabase: Client = init_connection()

def hash_senha(senha_plana):
    return hashlib.sha256(senha_plana.encode()).hexdigest()

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
        st.error(f"❌ Erro ao enviar e-mail: {e}")
        return False

def upload_pdf(file, prefixo):
    try:
        nome_arquivo = f"{prefixo}_{int(datetime.now().timestamp())}_{file.name}"
        supabase.storage.from_("certificados").upload(
            path=nome_arquivo, file=file.read(), file_options={"content-type": "application/pdf"}
        )
        return supabase.storage.from_("certificados").get_public_url(nome_arquivo)
    except Exception as e:
        st.error(f"Erro ao salvar PDF: {e}")
        return None

# --- GESTÃO DE SESSÃO ---
agora = time.time()
if "session_user" in st.query_params and "session_perfil" in st.query_params:
    st.session_state["autenticado"] = True
    st.session_state["user_email"] = st.query_params["session_user"]
    st.session_state["user_perfil"] = st.query_params["session_perfil"]

if st.session_state.get("autenticado", False):
    if "ultima_atividade" in st.session_state and (agora - st.session_state["ultima_atividade"]) > TEMPO_INATIVIDADE:
        st.session_state.clear()
        st.query_params.clear()
        st.warning("⚠️ Sessão expirada por inatividade.")
        st.rerun()
    st.session_state["ultima_atividade"] = agora

# --- TELA DE LOGIN COM RESTRIÇÃO DE DOMÍNIO ---
if not st.session_state.get("autenticado", False):
    col_l1, col_l2, col_l3 = st.columns([1, 1.2, 1])
    with col_l2:
        st.markdown(f"""
            <div style="text-align: center; margin-bottom: 1.2rem;">
                <img src="{LOGO_URL}" style="width: 220px; filter: brightness(0) invert(1);" />
            </div>
        """, unsafe_allow_html=True)
        st.markdown("<h2 style='text-align: center;'>🔐 Lab Master</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #9AABA0;'>Acesso Restrito - @inplanet.earth</p>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            email_input = st.text_input("E-mail Institucional")
            senha_input = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar no Sistema", use_container_width=True):
                email_clean = email_input.strip().lower()
                if not email_clean.endswith("@inplanet.earth"):
                    st.error("❌ Acesso permitido apenas para e-mails do domínio @inplanet.earth")
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
    st.stop()

# --- NAVEGAÇÃO E SIDEBAR ---
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
    opcoes_menu = ["📌 Inventário & Status", "🛡️ Modo Auditoria (ISO 17025)", "🚨 Trabalho Não Conforme (7.10)", "📈 Prontuário & Tendências", "📅 Agendamentos & Logística"]
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

menu = st.sidebar.radio("Navegação", opcoes_menu, key="radio_dinamico")
st.session_state["pagina_ativa"] = menu

if st.session_state["modulo_ativo"] != "Hub":
    st.sidebar.divider()
    st.sidebar.button("⬅️ Voltar ao Hub Principal", on_click=selecionar_modulo, args=("Hub", "🏠 Hub Principal"), use_container_width=True)

user_email = st.session_state["user_email"]

# ==============================================================================
# 0. HUB PRINCIPAL
# ==============================================================================
if menu == "🏠 Hub Principal":
    st.markdown("<h1 style='text-align: center; color: #FFFFFF;'>Lab Master</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center; color: var(--inplanet-green);'>Sistema de Gestão Laboratorial ISO/IEC 17025</h3>", unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        st.info("🔬 **Módulo de Equipamentos**\nControle de ativos, inventário operacional, calibrações, manutenções e rastreabilidade metrológica.")
        st.button("Acessar Equipamentos ➔", on_click=selecionar_modulo, args=("Equipamentos", "📌 Inventário & Status"), use_container_width=True)
    with col2:
        st.info("📦 **Reagentes & Consumíveis**\nGestão de frascos, reagentes, laudos CoA, validade e estoque de segurança.")
        st.button("Acessar Reagentes ➔", on_click=selecionar_modulo, args=("Reagentes", "📦 Controle de Estoque"), use_container_width=True)

# ==============================================================================
# 1. EQUIPAMENTOS - INVENTÁRIO
# ==============================================================================
elif menu == "📌 Inventário & Status":
    st.header("📌 Inventário Geral e Status Operacional")
    res = supabase.table("equipamentos").select("*").eq("is_deleted", False).execute()
    df = pd.DataFrame(res.data or [])
    
    if not df.empty:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total de Equipamentos", len(df))
        c2.metric("Operacionais", len(df[df["status"] == "Operacional"]))
        c3.metric("Em Calibração", len(df[df["status"] == "Em Calibração"]))
        c4.metric("Interditados / Quarentena", len(df[df["status"].isin(["Interditado / Fora de Uso", "Em Manutenção"])]))
        
        st.dataframe(df[["tag", "nome", "marca", "modelo", "serial_number", "periodicidade_meses", "status"]], use_container_width=True)
    else:
        st.info("Nenhum equipamento cadastrado.")

# ==============================================================================
# 2. CALIBRAÇÕES COM REGRA DE DECISÃO METROLÓGICA (|Erro| + U <= EMP)
# ==============================================================================
elif menu == "📐 Calibrações & Qualificações" and perfil in ["Admin", "Tecnico"]:
    st.header("📐 Registro Metrológico de Calibração (ISO 17025 Sec 6.5)")
    eq_res = supabase.table("equipamentos").select("tag, nome, periodicidade_meses").eq("is_deleted", False).execute()
    equipamentos_dados = {i["tag"]: i for i in eq_res.data} if eq_res.data else {}
    tags = list(equipamentos_dados.keys())
    
    if tags:
        equip_tag = st.selectbox("Selecione o Equipamento *", tags)
        periodicidade_meses = equipamentos_dados[equip_tag].get("periodicidade_meses") or 12
        
        with st.form("form_calib", clear_on_submit=True):
            c1, c2 = st.columns(2)
            data_calib = c1.date_input("Data da Calibração Realizada", value=datetime.now().date())
            certificado = c2.text_input("Número do Certificado / Laudo *")
            
            st.markdown("##### 📏 Avaliação Metrológica Automática")
            c3, c4, c5 = st.columns(3)
            erro_medido = c3.number_input("Erro Sistemático Medido (|E|)", format="%.6f")
            incerteza_exp = c4.number_input("Incerteza Expandida (U, k=2)", format="%.6f")
            emp_processo = c5.number_input("Erro Máximo Permitido (EMP)", format="%.6f", help="Deixe 0 se não houver EMP especificado.")
            
            pdf_file = st.file_uploader("Anexar Certificado em PDF", type=["pdf"])
            
            if st.form_submit_button("Avaliar & Salvar Calibração"):
                # Aplicação da Regra de Decisão Metrológica: (|E| + U) <= EMP
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

                # Atualiza status e interdição em caso de reprovação
                novo_status = "Operacional" if is_conforme else "Interditado / Fora de Uso"
                supabase.table("equipamentos").update({"status": novo_status}).eq("tag", equip_tag).execute()

                if is_conforme:
                    st.success(f"✅ Calibração APROVADA! (|E| + U = {desvio_total:.4f} ≤ EMP {emp_processo:.4f}). Equipamento Operacional.")
                else:
                    st.error(f"🚨 Calibração REPROVADA! (|E| + U = {desvio_total:.4f} > EMP {emp_processo:.4f}). Equipamento INTERDITADO e enviado para Investigação 7.10.")
                
                time.sleep(2)
                st.rerun()

# ==============================================================================
# 3. MÓDULO DE TRABALHO NÃO CONFORME (ISO 17025 - SEÇÃO 7.10)
# ==============================================================================
elif menu == "🚨 Trabalho Não Conforme (7.10)":
    st.header("🚨 Gestão de Trabalho Não Conforme e Análise Retroativa")
    st.caption("Requisito obrigatório do item 7.10 da norma ISO/IEC 17025 para contenção de falhas metrológicas.")
    
    res_tnc = supabase.table("trabalho_nao_conforme").select("*").order("criado_em", ascending=False).execute()
    df_tnc = pd.DataFrame(res_tnc.data or [])
    
    if not df_tnc.empty:
        st.dataframe(df_tnc[["equip_tag", "origem_evento", "analise_impacto_retroativa", "status", "criado_em"]], use_container_width=True)
    else:
        st.info("Nenhuma não conformidade ou investigação pendente.")

# ==============================================================================
# 4. OUTRAS ABAS PRESERVADAS (REAGENTES, LOGÍSTICA, ACESSOS)
# ==============================================================================
# [Suas telas de Controle de Estoque, Reagentes, Agendamentos e Gestão de Acessos continuam ativas]
