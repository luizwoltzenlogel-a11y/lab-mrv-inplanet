import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime
import hashlib
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

st.set_page_config(page_title="Lab Master - InPlanet", page_icon="🧪", layout="wide")

LOGO_URL = "https://cdn.prod.website-files.com/6a1be4c81b887a02620b0bb5/6a1ea2aab6347c3c4ae592a8_inplanet-logo.svg"

# --- CSS DEFINITIVO DE ALTO CONTRASTE ---
st.markdown("""
    <style>
    :root {
        --inplanet-dark: #121512;
        --inplanet-card: #1A201B;
        --inplanet-green: #3A6B52;
    }
    
    .stApp {
        background-color: var(--inplanet-dark) !important;
    }
    
    .stForm {
        background-color: var(--inplanet-card) !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        border-radius: 12px !important;
        padding: 2rem !important;
    }
    
    /* INPUTS BRANCOS COM BORDA VERDE */
    div[data-testid="stTextInput"] input,
    div[data-testid="stPasswordInput"] input,
    div[data-testid="stNumberInput"] input,
    div[data-testid="stDateInput"] input,
    div[data-testid="stSelectbox"] > div > div,
    div[data-testid="stTextArea"] textarea,
    div[data-baseweb="input"] > div,
    div[data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        border: 2px solid #3A6B52 !important;
        border-radius: 8px !important;
        opacity: 1 !important;
    }
    
    div[data-testid="stTextInput"] > div > div,
    div[data-testid="stPasswordInput"] > div > div,
    div[data-testid="stNumberInput"] > div > div,
    div[data-testid="stDateInput"] > div > div {
        background-color: #FFFFFF !important;
        border: 2px solid #3A6B52 !important;
        border-radius: 8px !important;
    }

    /* COR GRAFITE ESCURO EM TEXTOS E ÍCONES INTERNOS */
    div[data-testid="stTextInput"] input,
    div[data-testid="stPasswordInput"] input,
    div[data-testid="stNumberInput"] input,
    div[data-testid="stDateInput"] input,
    div[data-testid="stTextArea"] textarea,
    div[data-testid="stSelectbox"] *,
    div[data-baseweb="select"] *,
    div[data-baseweb="input"] * {
        color: #111411 !important;
        -webkit-text-fill-color: #111411 !important;
        font-weight: 600 !important;
    }

    div[data-testid="stSelectbox"] svg,
    div[data-testid="stDateInput"] svg,
    div[data-testid="stPasswordInput"] button svg {
        fill: #111411 !important;
        color: #111411 !important;
    }

    ul[role="listbox"],
    div[data-baseweb="popover"] *,
    div[data-baseweb="menu"] * {
        background-color: #FFFFFF !important;
        color: #111411 !important;
        -webkit-text-fill-color: #111411 !important;
        font-weight: 600 !important;
    }

    div[data-testid="stFileUploader"] > section {
        background-color: #FFFFFF !important;
        border: 2px dashed #3A6B52 !important;
        border-radius: 8px !important;
    }
    
    div[data-testid="stFileUploader"] > section * {
        color: #111411 !important;
        fill: #111411 !important;
        -webkit-text-fill-color: #111411 !important;
    }
    
    div[data-testid="stFileUploader"] > section button {
        background-color: var(--inplanet-green) !important;
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
    }

    div[data-testid="stTextInput"] label,
    div[data-testid="stPasswordInput"] label,
    div[data-testid="stNumberInput"] label,
    div[data-testid="stSelectbox"] label,
    div[data-testid="stTextArea"] label,
    div[data-testid="stDateInput"] label,
    div[data-testid="stFileUploader"] label {
        color: #F0F5F2 !important;
        -webkit-text-fill-color: #F0F5F2 !important;
        font-weight: 600 !important;
        font-size: 1rem !important;
    }
    
    .stButton > button {
        background-color: var(--inplanet-green) !important;
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 0.6rem 1rem !important;
    }
    
    .stButton > button:hover {
        background-color: #487F63 !important;
    }
    </style>
""", unsafe_allow_html=True)

@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase: Client = init_connection()

def hash_senha(senha_plana):
    return hashlib.sha256(senha_plana.encode()).hexdigest()

# --- BUSCA DINÂMICA DE GESTORES DO BANCO DE DADOS ---
def obter_lista_gestores():
    try:
        # Tenta buscar destinatários ativos cadastrados
        res = supabase.table("destinatarios_alertas").select("email").eq("ativo", True).execute()
        emails = [r["email"] for r in res.data] if res.data else []
        
        # Se não houver, busca e-mails com perfil Admin
        if not emails:
            res_users = supabase.table("usuarios").select("email").eq("perfil", "Admin").execute()
            emails = [r["email"] for r in res_users.data] if res_users.data else []
            
        return emails if emails else ["suporte@inplanet.earth"]
    except Exception:
        return ["suporte@inplanet.earth"]

# --- FUNÇÃO DISPARADORA DE E-MAILS VIA SMTP ---
def enviar_notificacao_email(destinatario, assunto, mensagem_corpo):
    try:
        if "smtp" in st.secrets:
            smtp_server = st.secrets["smtp"]["server"]
            smtp_port = st.secrets["smtp"]["port"]
            smtp_user = st.secrets["smtp"]["user"]
            smtp_password = st.secrets["smtp"]["password"]

            msg = MIMEMultipart()
            msg["From"] = smtp_user
            msg["To"] = destinatario
            msg["Subject"] = assunto
            msg.attach(MIMEText(mensagem_corpo, "plain"))

            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
            server.quit()
            st.info(f"📧 Notificação enviada para: {destinatario}")
        else:
            st.warning("⚠️ Configuração SMTP não encontrada nos Secrets. Alerta não enviado por e-mail.")
    except Exception as e:
        st.error(f"Erro ao enviar e-mail de alerta: {e}")

# --- GESTÃO DE SESSÃO E LOGIN ---
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
    st.session_state["user_email"] = ""
    st.session_state["user_perfil"] = ""

# TELA DE LOGIN
if not st.session_state["autenticado"]:
    col_l1, col_l2, col_l3 = st.columns([1, 1.2, 1])
    with col_l2:
        st.markdown(f"""
            <div style="text-align: center; width: 100%; margin-bottom: 1.2rem;">
                <img src="{LOGO_URL}" style="width: 220px; height: auto; filter: brightness(0) invert(1); display: inline-block;" />
            </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<h2 style='text-align: center; font-weight: 600; margin-top: -5px;'>🔐 Lab Master</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #9AABA0; margin-bottom: 1.5rem;'>Acesso Restrito - InPlanet Lab Management System</p>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            email_input = st.text_input("E-mail Institucional")
            senha_input = st.text_input("Senha", type="password")
            submit_login = st.form_submit_button("Entrar no Sistema", use_container_width=True)
            
            if submit_login:
                if email_input and senha_input:
                    senha_criptografada = hash_senha(senha_input)
                    res = supabase.table("usuarios").select("*").eq("email", email_input).eq("senha", senha_criptografada).execute()
                    
                    if res.data:
                        st.session_state["autenticado"] = True
                        st.session_state["user_email"] = res.data[0]["email"]
                        st.session_state["user_perfil"] = res.data[0]["perfil"]
                        st.rerun()
                    else:
                        st.error("❌ E-mail ou senha incorretos.")
                else:
                    st.warning("Preencha todos os campos.")
    st.stop()

# --- BARRA LATERAL ---
st.sidebar.markdown(f"""
    <div style="text-align: center; width: 100%; margin-bottom: 1rem;">
        <img src="{LOGO_URL}" style="width: 150px; height: auto; filter: brightness(0) invert(1); display: inline-block;" />
    </div>
""", unsafe_allow_html=True)

if os.path.exists("capivara.jpg"):
    st.sidebar.image("capivara.jpg", caption="Mascote Lab Master 🧪", use_container_width=True)
elif os.path.exists("capy.jpg"):
    st.sidebar.image("capy.jpg", caption="Mascote Lab Master 🧪", use_container_width=True)

st.sidebar.divider()

st.sidebar.title("👤 Meu Perfil")
st.sidebar.write(f"**E-mail:** {st.session_state['user_email']}")
st.sidebar.write(f"**Permissão:** {st.session_state['user_perfil']}")

if st.sidebar.button("🚪 Sair do Sistema"):
    st.session_state.clear()
    st.rerun()

st.sidebar.divider()

menus_disponiveis = ["Dashboard & Inventário", "Prontuário & Tendências"]
if st.session_state["user_perfil"] in ["Admin", "Tecnico"]:
    menus_disponiveis.extend(["Gerenciar Equipamentos", "Calibrações & Qualificações", "Manutenções & Intervenções"])
if st.session_state["user_perfil"] == "Admin":
    menus_disponiveis.append("Gestão de Acessos")

menu = st.sidebar.radio("Navegação", menus_disponiveis)
user_email = st.session_state["user_email"]

def upload_pdf(file, prefixo):
    try:
        timestamp = int(datetime.now().timestamp())
        nome_arquivo = f"{prefixo}_{timestamp}_{file.name}"
        conteudo = file.read()
        supabase.storage.from_("certificados").upload(
            path=nome_arquivo, file=conteudo, file_options={"content-type": "application/pdf"}
        )
        return supabase.storage.from_("certificados").get_public_url(nome_arquivo)
    except Exception as e:
        st.error(f"Erro ao salvar o PDF: {e}")
        return None

st.title("🧪 Lab Master - Gestão de Equipamentos")

# 1. DASHBOARD
if menu == "Dashboard & Inventário":
    st.header("📌 Inventário Geral e Status Operacional")
    res = supabase.table("equipamentos").select("*").execute()
    df = pd.DataFrame(res.data) if res.data else pd.DataFrame()
    
    if not df.empty:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total de Equipamentos", len(df))
        col2.metric("Operacionais", len(df[df["status"] == "Operacional"]))
        col3.metric("Em Calibração", len(df[df["status"] == "Em Calibração"]))
        col4.metric("Manutenção / Interditados", len(df[~df["status"].isin(["Operacional", "Em Calibração"])]))
        
        cols_exibir = ["tag", "nome", "marca", "modelo", "serial_number", "status"]
        if "modalidade_calibracao" in df.columns:
            cols_exibir.append("modalidade_calibracao")
        cols_exibir.append("registrado_por")
        
        st.dataframe(df[cols_exibir], use_container_width=True)

        st.divider()
        st.subheader("🗓️ Planejamento Logístico de Envio (Janelas de 30, 60 e 90 dias)")
        
        calib_res = supabase.table("calibracoes").select("equip_tag, data_venc, registrado_por").execute()
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
            m2.metric("⚠️ Médio Prazo (31 a 60 dias)", f"{len(df_60)} eq.")
            m3.metric("✈️ Longo Prazo (61 a 90 dias)", f"{len(df_90)} eq.")

            tab_30, tab_60, tab_90 = st.tabs([
                "🔴 Janela 1: Até 30 dias", 
                "🟡 Janela 2: 31 a 60 dias", 
                "🔵 Janela 3: 61 a 90 dias"
            ])

            cols_view = ['equip_tag', 'nome', 'marca', 'modalidade_calibracao', 'data_venc', 'dias_restantes', 'status'] if 'modalidade_calibracao' in df_calib.columns else ['equip_tag', 'nome', 'marca', 'data_venc', 'dias_restantes', 'status']

            with tab_30:
                st.dataframe(df_30[cols_view] if not df_30.empty else pd.DataFrame(), use_container_width=True)
            with tab_60:
                st.dataframe(df_60[cols_view] if not df_60.empty else pd.DataFrame(), use_container_width=True)
            with tab_90:
                st.dataframe(df_90[cols_view] if not df_90.empty else pd.DataFrame(), use_container_width=True)
    else:
        st.info("Nenhum equipamento cadastrado.")

# 2. PRONTUÁRIO & TENDÊNCIAS
elif menu == "Prontuário & Tendências":
    st.header("📈 Prontuário do Equipamento e Análise de Tendências")
    eq_res = supabase.table("equipamentos").select("tag, nome").execute()
    
    if eq_res.data:
        opcoes_eq = {f"{item['tag']} - {item['nome']}": item['tag'] for item in eq_res.data}
        selecionado = st.selectbox("Selecione o equipamento:", list(opcoes_eq.keys()))
        tag_alvo = opcoes_eq[selecionado]
        
        c_res = supabase.table("calibracoes").select("*").eq("equip_tag", tag_alvo).execute()
        m_res = supabase.table("manutencoes").select("*").eq("equip_tag", tag_alvo).execute()
        
        df_c = pd.DataFrame(c_res.data) if c_res.data else pd.DataFrame()
        df_m = pd.DataFrame(m_res.data) if m_res.data else pd.DataFrame()
        
        tot_corretivas = len(df_m[df_m["tipo"] == "Corretiva"]) if not df_m.empty and "tipo" in df_m.columns else 0
        tot_preventivas = len(df_m[df_m["tipo"] == "Preventiva"]) if not df_m.empty and "tipo" in df_m.columns else 0
        tot_reprovacoes = len(df_c[df_c["resultado"] == "Reprovado"]) if not df_c.empty and "resultado" in df_c.columns else 0
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Manutenções Corretivas", tot_corretivas)
        col2.metric("Manutenções Preventivas", tot_preventivas)
        col3.metric("Reprovações em Calibração", tot_reprovacoes)
        col4.metric("Total de Registros", len(df_c) + len(df_m))
        
        if tot_corretivas >= 2:
            st.error(f"🚨 **Alerta de Falha Crônica:** Este equipamento acumulou {tot_corretivas} manutenções corretivas.")
    else:
        st.info("Nenhum equipamento cadastrado.")

# 3. GERENCIAR EQUIPAMENTOS
elif menu == "Gerenciar Equipamentos":
    st.header("📝 Gestão de Equipamentos (Req. 6.4.13)")
    res_exist = supabase.table("equipamentos").select("*").execute()
    df_eq_exist = pd.DataFrame(res_exist.data) if res_exist.data else pd.DataFrame()
    
    abas = ["📝 Cadastrar / Editar", "📁 Importação em Massa"]
    if st.session_state["user_perfil"] == "Admin":
        abas.append("🗑️ Excluir Equipamento")
        tabs = st.tabs(abas)
        tab_ind, tab_massa, tab_exc = tabs[0], tabs[1], tabs[2]
    else:
        tabs = st.tabs(abas)
        tab_ind, tab_massa = tabs[0], tabs[1]
    
    with tab_ind:
        lista_tags = ["-- Cadastrar Novo Equipamento --"] + (df_eq_exist["tag"].tolist() if not df_eq_exist.empty else [])
        tag_selecionada = st.selectbox("Selecione para EDITAR um existente ou mantenha para NOVO:", lista_tags)
        
        def_tag, def_nome, def_marca, def_modelo, def_sn, def_status, def_mod = "", "", "", "", "", "Operacional", "Envio Externo"
        if tag_selecionada != "-- Cadastrar Novo Equipamento --" and not df_eq_exist.empty:
            row = df_eq_exist[df_eq_exist["tag"] == tag_selecionada].iloc[0]
            def_tag = str(row.get("tag", ""))
            def_nome = str(row.get("nome", ""))
            def_marca = str(row.get("marca", "")) if pd.notna(row.get("marca")) else ""
            def_modelo = str(row.get("modelo", "")) if pd.notna(row.get("modelo")) else ""
            def_sn = str(row.get("serial_number", "")) if pd.notna(row.get("serial_number")) else ""
            def_status = str(row.get("status", "Operacional"))
            def_mod = str(row.get("modalidade_calibracao", "Envio Externo"))
            
        with st.form("form_equip", clear_on_submit=False):
            col1, col2 = st.columns(2)
            with col1:
                tag = st.text_input("Tag / Código Interno", value=def_tag)
                nome = st.text_input("Nome do Equipamento", value=def_nome)
                marca = st.text_input("Marca / Fabricante", value=def_marca)
                opcoes_mod = ["Envio Externo", "In-Loco", "Qualificação OQ/PQ"]
                idx_mod = opcoes_mod.index(def_mod) if def_mod in opcoes_mod else 0
                modalidade = st.selectbox("Modalidade de Serviço", opcoes_mod, index=idx_mod)
            with col2:
                modelo = st.text_input("Modelo", value=def_modelo)
                serial_number = st.text_input("Número de Série", value=def_sn)
                opcoes_status = ["Operacional", "Em Calibração", "Em Manutenção", "Interditado / Fora de Uso"]
                idx_status = opcoes_status.index(def_status) if def_status in opcoes_status else 0
                status = st.selectbox("Status Operacional", opcoes_status, index=idx_status)
            
            label_btn = "Atualizar Equipamento" if tag_selecionada != "-- Cadastrar Novo Equipamento --" else "Salvar Novo Equipamento"
            if st.form_submit_button(label_btn):
                if tag and nome:
                    dado = {
                        "tag": tag, "nome": nome, "marca": marca, "modelo": modelo, 
                        "serial_number": serial_number, "status": status, 
                        "modalidade_calibracao": modalidade, "registrado_por": user_email
                    }
                    supabase.table("equipamentos").upsert(dado, on_conflict="tag").execute()
                    st.success(f"Equipamento {tag} gravado!")
                    st.rerun()

# 4. CALIBRAÇÕES (SELEÇÃO OBRIGATÓRIA DE GESTOR PARA ALERTAS)
elif menu == "Calibrações & Qualificações":
    st.header("📐 Registro de Calibração")
    eq_res = supabase.table("equipamentos").select("tag").execute()
    tags = [item["tag"] for item in eq_res.data] if eq_res.data else []
    lista_gestores = obter_lista_gestores()
    
    if tags:
        with st.form("form_calib", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                equip_tag = st.selectbox("Equipamento *", tags)
                data_calib = st.date_input("Data da Calibração")
                resultado = st.selectbox("Resultado *", ["Aprovado", "Reprovado"])
            with col2:
                data_venc = st.date_input("Próximo Vencimento")
                certificado = st.text_input("Número do Certificado")
                gestor_notificar = st.selectbox("Gestor / Responsável a Notificar em Alertas *", lista_gestores)
                
            pdf_file = st.file_uploader("Anexar Certificado (PDF)", type=["pdf"])
            
            if st.form_submit_button("Registrar Calibração"):
                pdf_url = upload_pdf(pdf_file, f"CALIB_{equip_tag}") if pdf_file else None
                dado = {"equip_tag": equip_tag, "data_calib": str(data_calib), "data_venc": str(data_venc), "resultado": resultado, "certificado": certificado, "pdf_url": pdf_url, "registrado_por": user_email}
                supabase.table("calibracoes").insert(dado).execute()
                
                novo_status = "Operacional" if resultado == "Aprovado" else "Interditado / Fora de Uso"
                supabase.table("equipamentos").update({"status": novo_status}).eq("tag", equip_tag).execute()
                
                # Se reprovado, envia e-mail diretamente ao Gestor selecionado
                if resultado == "Reprovado":
                    enviar_notificacao_email(
                        destinatario=gestor_notificar,
                        assunto=f"🚨 [Lab Master] Reprovação de Calibração: {equip_tag}",
                        mensagem_corpo=f"Atenção Gestor,\n\nO equipamento {equip_tag} foi REPROVADO na calibração e seu status foi alterado para 'Interditado / Fora de Uso'.\n\nCertificado: {certificado}\nRegistrado por: {user_email}"
                    )
                
                st.success(f"Calibração registrada! Status atualizado para '{novo_status}'.")
                st.rerun()

# 5. MANUTENÇÕES (SELEÇÃO OBRIGATÓRIA DE GESTOR PARA ALERTAS)
elif menu == "Manutenções & Intervenções":
    st.header("🛠️ Registro de Manutenção")
    eq_res = supabase.table("equipamentos").select("tag").execute()
    tags = [item["tag"] for item in eq_res.data] if eq_res.data else []
    lista_gestores = obter_lista_gestores()
    
    if tags:
        with st.form("form_manut", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                equip_tag = st.selectbox("Equipamento *", tags)
                tipo = st.selectbox("Tipo de Intervenção *", ["Preventiva", "Corretiva", "Ajuste / Qualificação"])
                data_intervencao = st.date_input("Data")
                tecnico = st.text_input("Técnico / Empresa Responsável")
            with col2:
                status_pos = st.selectbox("Status Pós-Manutenção *", ["Operacional", "Em Calibração", "Em Manutenção", "Interditado / Fora de Uso"])
                gestor_notificar = st.selectbox("Gestor / Responsável a Notificar *", lista_gestores)
                descricao = st.text_area("Descrição detalhada da intervenção")
                
            pdf_file = st.file_uploader("Anexar Relatório (PDF)", type=["pdf"])
            
            if st.form_submit_button("Registrar Manutenção"):
                pdf_url = upload_pdf(pdf_file, f"MANUT_{equip_tag}") if pdf_file else None
                dado = {"equip_tag": equip_tag, "tipo": tipo, "data_intervencao": str(data_intervencao), "tecnico": tecnico, "descricao": descricao, "pdf_url": pdf_url, "registrado_por": user_email}
                supabase.table("manutencoes").insert(dado).execute()
                supabase.table("equipamentos").update({"status": status_pos}).eq("tag", equip_tag).execute()
                
                # Regra 1: Manutenção Corretiva ou Equipamento Inoperante -> Notifica o Gestor Selecionado
                if tipo == "Corretiva" or status_pos in ["Interditado / Fora de Uso", "Em Manutenção"]:
                    enviar_notificacao_email(
                        destinatario=gestor_notificar,
                        assunto=f"⚠️ [Lab Master] Alerta de Manutenção/Indisponibilidade: {equip_tag}",
                        mensagem_corpo=f"Prezado(a) Gestor(a),\n\nFoi registrada uma intervenção que requer sua atenção.\n\nEquipamento: {equip_tag}\nTipo: {tipo}\nTécnico/Empresa: {tecnico}\nNovo Status: {status_pos}\nDescrição: {descricao}\n\nRegistrado por: {user_email}"
                    )
                
                st.success("Manutenção registrada e e-mail de alerta enviado ao Gestor selecionado!")
                st.rerun()

# 6. GESTÃO DE ACESSOS & ALERTAS (Apenas Admin)
elif menu == "Gestão de Acessos":
    st.header("👥 Gestão de Usuários e Destinatários de Alertas")
    tab_users, tab_alertas = st.tabs(["👤 Controle de Usuários", "📩 Destinatários de Alertas por E-mail"])
    
    with tab_users:
        res_users = supabase.table("usuarios").select("id, email, perfil, criado_em").execute()
        if res_users.data:
            st.dataframe(pd.DataFrame(res_users.data)[["email", "perfil", "criado_em"]], use_container_width=True)

    with tab_alertas:
        st.subheader("📋 Lista de Gestores e Destinatários dos Relatórios")
        st.caption("Cadastre ou ative os e-mails nesta lista para que apareçam como opção nos formulários de notificação.")
        try:
            res_dest = supabase.table("destinatarios_alertas").select("*").execute()
            df_dest = pd.DataFrame(res_dest.data) if res_dest.data else pd.DataFrame()
            if not df_dest.empty:
                st.dataframe(df_dest[["email", "ativo", "criado_em"]], use_container_width=True)
            else:
                st.info("Nenhum e-mail cadastrado na lista de notificações.")
        except Exception:
            st.warning("⚠️ Execute o comando SQL no Supabase para ativar a tabela de destinatários de alertas.")
