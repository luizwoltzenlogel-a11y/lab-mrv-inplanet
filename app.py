import hashlib
import os
import smtplib
import time
import re
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd
import streamlit as st
from supabase import Client, create_client

st.set_page_config(page_title="Lab Master - InPlanet", page_icon="🧪", layout="wide")

LOGO_URL = "https://cdn.prod.website-files.com/6a1be4c81b887a02620b0bb5/6a1ea2aab6347c3c4ae592a8_inplanet-logo.svg"
TEMPO_INATIVIDADE = 600

# --- CSS DE ALTO CONTRASTE E ESTILIZAÇÃO DOS HUB CARDS ---
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

    /* INPUTS GERAIS */
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

    /* OVERRIDE DA CAIXA DE DATA */
    div[data-testid="stDateInput"] { background-color: transparent !important; }
    div[data-testid="stDateInput"] *,
    div[data-testid="stDateInput"] div,
    div[data-testid="stDateInput"] input,
    div[data-testid="stDateInput"] [data-baseweb="input"],
    div[data-testid="stDateInput"] [data-baseweb="base-input"] {
        background-color: #FFFFFF !important;
        color: #000000 !important;
        -webkit-text-fill-color: #000000 !important;
        font-weight: 600 !important;
    }
    div[data-testid="stDateInput"] [data-baseweb="input"] {
        border: 2px solid var(--inplanet-green) !important;
        border-radius: 8px !important;
    }

    /* DROPDOWNS E CALENDÁRIOS */
    ul[role="listbox"], div[data-baseweb="popover"], div[data-baseweb="menu"],
    div[data-baseweb="datepicker"], div[data-baseweb="calendar"] {
        background-color: #FFFFFF !important;
    }
    ul[role="listbox"] *, div[data-baseweb="popover"] *, div[data-baseweb="menu"] *,
    div[data-baseweb="datepicker"] *, div[data-baseweb="calendar"] * {
        background-color: #FFFFFF !important;
        color: #000000 !important;
        -webkit-text-fill-color: #000000 !important;
        font-weight: 600 !important;
    }

    /* ÍCONES */
    div[data-testid="stSelectbox"] svg, div[data-testid="stDateInput"] svg,
    div[data-testid="stPasswordInput"] button svg {
        fill: #000000 !important;
        color: #000000 !important;
        background-color: transparent !important;
    }

    /* UPLOAD DE ARQUIVOS */
    div[data-testid="stFileUploader"] > section {
        background-color: #FFFFFF !important;
        border: 2px dashed var(--inplanet-green) !important;
        border-radius: 8px !important;
    }
    div[data-testid="stFileUploader"] section div, div[data-testid="stFileUploader"] section span {
        color: #000000 !important;
        -webkit-text-fill-color: #000000 !important;
    }

    /* BOTÕES */
    .stButton > button, div[data-testid="stFormSubmitButton"] > button,
    div[data-testid="stFileUploader"] section button {
        background-color: var(--inplanet-green) !important;
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 0.6rem 1rem !important;
    }
    .stButton > button:hover, div[data-testid="stFormSubmitButton"] > button:hover { 
        background-color: #487F63 !important; 
    }

    /* LABELS E EXPANDERS (ESQUECI A SENHA) */
    div[data-testid="stTextInput"] label, div[data-testid="stPasswordInput"] label,
    div[data-testid="stNumberInput"] label, div[data-testid="stSelectbox"] label,
    div[data-testid="stTextArea"] label, div[data-testid="stDateInput"] label,
    div[data-testid="stFileUploader"] label {
        color: #F0F5F2 !important;
        -webkit-text-fill-color: #F0F5F2 !important;
        background-color: transparent !important;
        font-weight: 600 !important;
    }
    
    div[data-testid="stExpander"] details summary p {
        color: #F0F5F2 !important;
        font-weight: 600 !important;
        font-size: 1.05rem !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- CONEXÃO E FUNÇÕES AUXILIARES ---
@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

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
        return
    try:
        msg = MIMEMultipart()
        msg["From"] = smtp_cfg["user"]
        msg["To"] = destinatario
        msg["Subject"] = assunto
        msg.attach(MIMEText(mensagem_corpo, "plain"))

        with smtplib.SMTP(smtp_cfg["server"], int(smtp_cfg["port"])) as server:
            server.starttls()
            server.login(smtp_cfg["user"], smtp_cfg["password"])
            server.send_message(msg)
    except Exception as e:
        st.error(f"Erro ao enviar e-mail: {e}")

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

def exibir_mascote():
    for img in ["capivara.jpg", "capy.jpg", "capivara.png"]:
        if os.path.exists(img):
            st.sidebar.image(img, use_container_width=True)
            break

# --- GESTÃO DE SESSÃO E TIMEOUT ---
agora = time.time()
if "session_user" in st.query_params and "session_perfil" in st.query_params:
    st.session_state["autenticado"] = True
    st.session_state["user_email"] = st.query_params["session_user"]
    st.session_state["user_perfil"] = st.query_params["session_perfil"]

if st.session_state.get("autenticado", False):
    if "ultima_atividade" in st.session_state and (agora - st.session_state["ultima_atividade"]) > TEMPO_INATIVIDADE:
        st.session_state.clear()
        st.query_params.clear()
        st.warning("⚠️ Sessão expirada após 10 minutos de inatividade. Faça login novamente.")
        st.rerun()
    st.session_state["ultima_atividade"] = agora

    st.components.v1.html("""
        <script>
        var timer = new Date().getTime();
        const reset = () => { timer = new Date().getTime(); };
        ['mousemove', 'keypress', 'click', 'scroll'].forEach(e => window.addEventListener(e, reset));
        setInterval(() => { if (new Date().getTime() - timer >= 600000) window.location.reload(); }, 15000);
        </script>
    """, height=0, width=0)

# --- TELA DE LOGIN ---
if not st.session_state.get("autenticado", False):
    col_l1, col_l2, col_l3 = st.columns([1, 1.2, 1])
    with col_l2:
        logo_login = None
        for nome_img in ["logo_labmaster.jpg", "logo_labmaster.png", "logo_labmaster.jpeg", "Quero_um_logo_de_capivara_bpede_minimalista_com_contorno_brn.jpg"]:
            if os.path.exists(nome_img):
                logo_login = nome_img
                break
                
        if logo_login:
            st.image(logo_login, use_container_width=True)
        else:
            st.markdown(f"""
                <div style="text-align: center; margin-bottom: 1.2rem;">
                    <a href="/" target="_self"><img src="{LOGO_URL}" style="width: 220px; filter: brightness(0) invert(1);" /></a>
                </div>
            """, unsafe_allow_html=True)
            st.markdown("<h2 style='text-align: center;'>🔐 Lab Master</h2>", unsafe_allow_html=True)
            
        st.markdown("<p style='text-align: center; color: #9AABA0;'>Acesso Restrito - InPlanet LMS</p>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            email_input = st.text_input("E-mail Institucional")
            senha_input = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar no Sistema", use_container_width=True):
                if email_input and senha_input:
                    res = supabase.table("usuarios").select("*").eq("email", email_input).eq("senha", hash_senha(senha_input)).execute()
                    if res.data:
                        st.session_state.update({"autenticado": True, "user_email": res.data[0]["email"], "user_perfil": res.data[0]["perfil"], "ultima_atividade": time.time()})
                        st.query_params["session_user"] = res.data[0]["email"]
                        st.query_params["session_perfil"] = res.data[0]["perfil"]
                        st.rerun()
                    else:
                        st.error("❌ E-mail ou senha incorretos.")
                else:
                    st.warning("Preencha todos os campos.")
        
        with st.expander("🔑 Esqueci minha senha"):
            with st.form("reset_form"):
                email_reset = st.text_input("Digite seu E-mail Institucional para solicitar o reset")
                if st.form_submit_button("Solicitar Nova Senha", use_container_width=True):
                    if email_reset:
                        gestores = obter_lista_gestores()
                        assunto = f"🔐 Solicitação de Reset de Senha: {email_reset}"
                        corpo = f"Atenção Administrador,\n\nO usuário '{email_reset}' solicitou o reset de senha de acesso ao Lab Master.\n\nAcesse o sistema, vá até o menu 'Gestão de Acessos' e atualize a senha deste usuário."
                        
                        enviado = False
                        for gestor in gestores:
                            enviar_notificacao_email(gestor, assunto, corpo)
                            enviado = True
                            
                        if enviado:
                            st.success("✅ Solicitação enviada! Um administrador entrará em contato em breve.")
                            time.sleep(3)
                            st.rerun()
                    else:
                        st.warning("⚠️ Por favor, informe o seu e-mail institucional.")
                        
    st.stop()

# --- NAVEGAÇÃO E RBAC ---
def selecionar_modulo(nome_modulo, pagina_inicial):
    st.session_state["modulo_ativo"] = nome_modulo
    st.session_state["pagina_ativa"] = pagina_inicial

if "modulo_ativo" not in st.session_state:
    st.session_state["modulo_ativo"] = "Hub"
if "pagina_ativa" not in st.session_state:
    st.session_state["pagina_ativa"] = "🏠 Hub Principal"

home_link = f"/?session_user={st.session_state['user_email']}&session_perfil={st.session_state['user_perfil']}"
st.sidebar.markdown(f"""
    <div style="text-align: center; margin-bottom: 1rem;">
        <a href="{home_link}" target="_self"><img src="{LOGO_URL}" style="width: 150px; filter: brightness(0) invert(1);" /></a>
    </div>
""", unsafe_allow_html=True)

exibir_mascote()
st.sidebar.divider()
st.sidebar.title("👤 Meu Perfil")
st.sidebar.write(f"**E-mail:** {st.session_state['user_email']}")
st.sidebar.write(f"**Permissão:** {st.session_state['user_perfil']}")

if st.sidebar.button("🚪 Sair do Sistema"):
    st.session_state.clear()
    st.query_params.clear()
    st.rerun()

st.sidebar.divider()

perfil = st.session_state["user_perfil"]

if st.session_state["modulo_ativo"] == "Equipamentos":
    st.sidebar.markdown("### 🔬 Módulo Equipamentos")
    opcoes_menu = ["📌 Inventário & Status", "🛡️ Modo Auditoria (ISO 17025)", "📈 Prontuário & Tendências"]
    if
