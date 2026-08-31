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
from PIL import Image

# Configuração da Página
st.set_page_config(page_title="Lab Master - InPlanet LMS", page_icon="🧪", layout="wide")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPO_INATIVIDADE = 600

# --- RESOLUÇÃO ABSOLUTA DA LOGO DA CAPIVARA ---
def obter_caminho_logo():
    """Garante a localização da imagem da capivara independente do SO/Linux no Streamlit Cloud."""
    candidatos = [
        "logo_labmaster.jpg", "logo_labmaster.jpeg", "logo_labmaster.png",
        "capivara.jpg", "capivara.png", "logo.png"
    ]
    for nome in candidatos:
        caminho_completo = os.path.join(BASE_DIR, nome)
        if os.path.exists(caminho_completo):
            return caminho_completo
    return None

def renderizar_logo(largura=200):
    caminho = obter_caminho_logo()
    if caminho:
        st.image(caminho, width=largura)
    else:
        st.markdown(f"""
            <div style="text-align: center; margin-bottom: 1rem;">
                <h1 style="color: #3A6B52; font-size: 2.2rem; font-weight: 800;">🧪 Lab Master</h1>
                <p style="color: #9AABA0; margin-top: -10px;">InPlanet LMS - ISO/IEC 17025</p>
            </div>
        """, unsafe_allow_html=True)

# --- CSS DE ALTO CONTRASTE (ESTILO INPLANET) ---
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
            st.error("⚠️ Secrets 'SUPABASE_URL' ou 'SUPABASE_KEY' ausentes.")
            st.stop()
        return create_client(url, key)
    except Exception as e:
        st.error(f"❌ Erro ao conectar com Supabase: {e}")
        st.stop()

supabase: Client = init_connection()

# --- FUNÇÕES DE SUPORTE E NOTIFICAÇÃO SMTP ---
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
            st.error(f"Erro de consulta na tabela 'equipamentos': {e}")
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
        st.error(f"❌ Falha ao enviar e-mail: {e}")
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

# --- GERENCIAMENTO DE SESSÃO E EXPIRAÇÃO POR INATIVIDADE ---
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

# --- TELA DE LOGIN COM VALIDAÇÃO DE DOMÍNIO ---
if not st.session_state.get("autenticado", False):
    col_l1, col_l2, col_l3 = st.columns([1, 1.2, 1])
    with col_l2:
        renderizar_logo(largura=220)
        st.markdown("<h2 style='text-align: center;'>🔐 Lab Master</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #9AABA0;'>Acesso Restrito - @inplanet.earth</p>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            email_input = st.text_input("E-mail Institucional")
            senha_input = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar no Sistema", use_container_width=True):
                email_clean = email_input.strip().lower()
                if not email_clean.endswith("@inplanet.earth"):
                    st.error("❌ Somente e-mails do domínio corporativo @inplanet.earth são autorizados.")
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
                        st.error("❌ Credenciais inválidas.")
                else:
                    st.warning("Preencha todos os campos.")
    st.stop()

# --- SIDEBAR E NAVEGAÇÃO ---
def selecionar_modulo(nome_modulo, pagina_inicial):
    st.session_state["modulo_ativo"] = nome_modulo
    st.session_state["pagina_ativa"] = pagina_inicial

if "modulo_ativo" not in st.session_state:
    st.session_state["modulo_ativo"] = "Hub"
if "pagina_ativa" not in st.session_state:
    st.session_state["pagina_ativa"] = "🏠 Hub Principal"

with st.sidebar:
    renderizar_logo(largura=140)
    st.divider()
    st.title("👤 Meu Perfil")
    st.write(f"**E-mail:** {st.session_state['user_email']}")
    st.write(f"**Permissão:** {st.session_state['user_perfil']}")
    
    if st.button("🚪 Sair do Sistema", use_container_width=True):
        st.session_state.clear()
        st.query_params.clear()
        st.rerun()

st.sidebar.divider()
perfil = st.session_state["user_perfil"]

if st.session_state["modulo_ativo"] == "Equipamentos":
    st.sidebar.markdown("### 🔬 Módulo Equipamentos")
    opcoes_menu = [
        "📌 Inventário & Status", 
        "🧪 Admissão ('Estado Zero')",
        "🛡️ Modo Auditoria (ISO 17025)", 
        "🚨 Ocorrências & Seção 7.10", 
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
    col_h1, col_h2, col_h3 = st.columns([1, 1.2, 1])
    with col_h2:
        renderizar_logo(largura=260)
        
    st.markdown("<h3 style='text-align: center; color: var(--inplanet-green); font-weight: 600;'>Sistema de Gestão Laboratorial ISO/IEC 17025</h3>", unsafe_allow_html=True)
    
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
        st.button("Acessar Equipamentos ➔", on_click=selecionar_modulo, args=("Equipamentos", "📌 Inventário & Status"), use_container_width=True, key="btn_hub_eq")

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
        st.button("Acessar Reagentes ➔", on_click=selecionar_modulo, args=("Reagentes", "📦 Controle de Estoque"), use_container_width=True, key="btn_hub_reag")

# ==============================================================================
# 1. INVENTÁRIO & STATUS OPERACIONAL (ITEM 6.4)
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
    else:
        st.info("Nenhum equipamento cadastrado.")

# ==============================================================================
# 2. ADMISSÃO DE EQUIPAMENTOS NOVOS ("ESTADO ZERO")
# ==============================================================================
elif menu == "🧪 Admissão ('Estado Zero')":
    st.header("🧪 Comissionamento e Liberação Técnica de Equipamentos Novos")
    st.caption("Conforme a ISO 17025, equipamentos novos permanecem bloqueados para ensaios até a aprovação do 1º certificado.")
    
    dados_eq = buscar_equipamentos_seguro()
    df_eq = pd.DataFrame(dados_eq) if dados_eq else pd.DataFrame()
    
    if not df_eq.empty and "status" in df_eq.columns:
        df_comm = df_eq[df_eq["status"] == "Em Comissionamento"]
        if not df_comm.empty:
            st.dataframe(df_comm[["tag", "nome", "marca", "modelo", "serial_number"]], use_container_width=True)
        else:
            st.info("Nenhum equipamento em fase de comissionamento ('Estado Zero').")
    else:
        st.info("Sem dados disponíveis.")

# ==============================================================================
# 3. MÓDULO DE OCORRÊNCIAS & TRABALHO NÃO CONFORME (ITEM 7.10)
# ==============================================================================
elif menu == "🚨 Ocorrências & Seção 7.10":
    st.header("🚨 Logbook de Ocorrências e Trabalho Não Conforme (7.10)")
    
    tab1, tab2 = st.tabs(["📝 Logbook / Inserir Evento", "🔍 Investigação Retroativa 7.10"])
    
    with tab1:
        dados_eq = buscar_equipamentos_seguro()
        if dados_eq:
            dict_eq = {f"{e['tag']} - {e['nome']}": e['tag'] for e in dados_eq}
            sel_label = st.selectbox("Equipamento Relacionado *", list(dict_eq.keys()))
            tag_sel = dict_eq[sel_label]
            
            with st.form("form_evento_log"):
                tipo_ev = st.selectbox("Tipo de Evento *", [
                    "FALHA_QUEBRA", "ENVIO_CALIBRACAO", "ENVIO_MANUTENCAO", 
                    "RETORNO_FORNECEDOR", "MUDANCA_LOCAL"
                ])
                desc = st.text_area("Descrição Detalhada da Ocorrência *")
                fornecedor = st.text_input("Fornecedor / Laboratório Externo (se aplicável)")
                
                if st.form_submit_button("Registrar Ocorrência"):
                    supabase.table("eventos_logbook").insert({
                        "equip_tag": tag_sel,
                        "tipo_evento": tipo_ev,
                        "descricao": desc,
                        "fornecedor_nome": fornecedor,
                        "registrado_por": user_email
                    }).execute()
                    
                    if tipo_ev == "FALHA_QUEBRA":
                        supabase.table("equipamentos").update({"status": "Interditado / Fora de Uso"}).eq("tag", tag_sel).execute()
                        supabase.table("trabalho_nao_conforme").insert({
                            "equip_tag": tag_sel,
                            "origem_evento": "Falha Operacional Registrada no Logbook",
                            "analise_impacto_retroativa": f"INVESTIGAÇÃO AUTOMÁTICA ISO 17025 (SEÇÃO 7.10): Equipamento {tag_sel} apresentou falha. Avaliar a validade dos ensaios executados desde a última checagem.",
                            "registrado_por": user_email
                        }).execute()
                        st.error(f"🚨 Falha registrada! Equipamento {tag_sel} INTERDITADO e enviado para investigação do item 7.10.")
                    else:
                        st.success("Ocorrência gravada com sucesso!")
                    time.sleep(2)
                    st.rerun()

    with tab2:
        try:
            res_tnc = supabase.table("trabalho_nao_conforme").select("*").order("criado_em", ascending=False).execute()
            df_tnc = pd.DataFrame(res_tnc.data or [])
            if not df_tnc.empty:
                st.dataframe(df_tnc[["equip_tag", "origem_evento", "analise_impacto_retroativa", "status", "criado_em"]], use_container_width=True)
            else:
                st.info("Nenhuma investigação de trabalho não conforme aberta no momento.")
        except Exception as e:
            st.warning(f"Tabela de Trabalho Não Conforme pendente de inicialização: {e}")

# ==============================================================================
# 4. CALIBRAÇÕES E REGRA DE DECISÃO METROLÓGICA (|E| + U <= EMP)
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
            
            st.markdown("##### 📏 Avaliação Metrológica Automática")
            c3, c4, c5 = st.columns(3)
            erro_medido = c3.number_input("Erro Sistemático Medido (|E|)", format="%.6f")
            incerteza_exp = c4.number_input("Incerteza Expandida (U, k=2)", format="%.6f")
            emp_processo = c5.number_input("Erro Máximo Permitido (EMP)", format="%.6f")
            
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
                        "origem_evento": f"Reprovação Metrológica no Certificado {certificado}",
                        "analise_impacto_retroativa": f"INVESTIGAÇÃO AUTOMÁTICA ISO 17025 (SEÇÃO 7.10): (|E| + U = {desvio_total:.6f} > EMP {emp_processo:.6f}). Avaliar ensaios executados.",
                        "registrado_por": user_email
                    }).execute()
                    st.error(f"🚨 Calibração REPROVADA! (|E| + U = {desvio_total:.6f} > EMP {emp_processo:.6f}). Equipamento INTERDITADO.")
                else:
                    st.success(f"✅ Calibração APROVADA! (|E| + U = {desvio_total:.6f} ≤ EMP {emp_processo:.6f}). Equipamento Operacional.")
                    
                time.sleep(2)
                st.rerun()

# ==============================================================================
# 5. DEMAIS MÓDULOS (REAGENTES, LOGÍSTICA, GERENCIAMENTO, ACESSOS)
# ==============================================================================
elif menu == "📦 Controle de Estoque":
    st.header("📦 Gestão de Reagentes, Consumíveis e Laudos CoA (Req. 6.6)")
    try:
        res_cat = supabase.table("reagentes").select("*").execute()
        df_cat = pd.DataFrame(res_cat.data or [])
        if not df_cat.empty:
            st.dataframe(df_cat, use_container_width=True)
        else:
            st.info("Nenhum reagente cadastrado no estoque.")
    except Exception as e:
        st.warning(f"Tabela de reagentes não encontrada: {e}")

elif menu == "📝 Gerenciar Equipamentos" and perfil in ["Admin", "Tecnico"]:
    st.header("📝 Cadastrar Equipamento com Tag Padrão (AAAA-NNN)")
    with st.form("form_cad_eq_padrão"):
        c1, c2 = st.columns(2)
        tag = c1.text_input("Tag / Código Interno (ex: BALA-001) *")
        nome = c2.text_input("Nome do Equipamento *")
        marca = c1.text_input("Marca *")
        modelo = c2.text_input("Modelo *")
        serial = c1.text_input("Número de Série *")
        period = c2.number_input("Periodicidade de Calibração (Meses)", min_value=1, value=12)
        
        if st.form_submit_button("Cadastrar Ativo"):
            tag_clean = tag.strip().upper()
            if not re.match(r'^[A-Z]{4}-\d{3}$', tag_clean):
                st.error("❌ A Tag deve seguir o padrão estrito de 4 letras, hífen e 3 dígitos (Ex: BALA-001).")
            elif tag_clean and nome:
                supabase.table("equipamentos").upsert({
                    "tag": tag_clean,
                    "nome": nome,
                    "marca": marca,
                    "modelo": modelo,
                    "serial_number": serial,
                    "periodicidade_meses": int(period),
                    "status": "Em Comissionamento",
                    "registrado_por": user_email
                }, on_conflict="tag").execute()
                st.success(f"Equipamento {tag_clean} cadastrado com sucesso!")
                st.rerun()

elif menu == "👥 Gestão de Acessos" and perfil == "Admin":
    st.header("👥 Gestão de Usuários (@inplanet.earth)")
    try:
        res_u = supabase.table("usuarios").select("email, perfil, criado_em").execute()
        if res_u.data:
            st.dataframe(pd.DataFrame(res_u.data), use_container_width=True)
    except Exception as e:
        st.error(f"Erro ao carregar usuários: {e}")
