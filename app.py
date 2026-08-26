import hashlib
import os
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd
import streamlit as st
from supabase import Client, create_client

st.set_page_config(page_title="Lab Master - InPlanet", page_icon="🧪", layout="wide")

LOGO_URL = "https://cdn.prod.website-files.com/6a1be4c81b887a02620b0bb5/6a1ea2aab6347c3c4ae592a8_inplanet-logo.svg"
TEMPO_INATIVIDADE = 600

# --- CSS RIGOROSO E COMPLETO PARA TODOS OS ELEMENTOS DO FORMULÁRIO ---
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

    /* 1. FORÇAR FUNDO BRANCO E BORDA VERDE EM TODOS OS INPUTS (INCLUINDO DATA) */
    div[data-testid="stTextInput"] input,
    div[data-testid="stPasswordInput"] input,
    div[data-testid="stNumberInput"] input,
    div[data-testid="stDateInput"] input,
    div[data-testid="stDateInput"] > div,
    div[data-testid="stDateInput"] div[data-baseweb="input"],
    div[data-testid="stSelectbox"] > div > div,
    div[data-testid="stTextArea"] textarea,
    div[data-baseweb="input"],
    div[data-baseweb="input"] > div,
    div[data-baseweb="select"] > div,
    div[data-baseweb="base-input"] {
        background-color: #FFFFFF !important;
        border: 2px solid var(--inplanet-green) !important;
        border-radius: 8px !important;
        opacity: 1 !important;
    }

    /* 2. FORÇAR TEXTO E ÍCONES PRETO ABSOLUTO EM CAMPOS DE DATA E SELEÇÃO */
    div[data-testid="stTextInput"] input,
    div[data-testid="stPasswordInput"] input,
    div[data-testid="stNumberInput"] input,
    div[data-testid="stDateInput"] input,
    div[data-testid="stDateInput"] *,
    div[data-testid="stTextArea"] textarea,
    div[data-testid="stSelectbox"] *,
    div[data-baseweb="select"] *,
    div[data-baseweb="input"] *,
    div[data-baseweb="popover"] *,
    div[data-baseweb="menu"] *,
    div[data-baseweb="datepicker"] *,
    div[data-baseweb="calendar"] *,
    ul[role="listbox"] * {
        color: #000000 !important;
        -webkit-text-fill-color: #000000 !important;
        font-weight: 600 !important;
    }

    /* Fundo dos Calendários e Popovers */
    ul[role="listbox"],
    div[data-baseweb="popover"],
    div[data-baseweb="menu"],
    div[data-baseweb="datepicker"],
    div[data-baseweb="calendar"] {
        background-color: #FFFFFF !important;
    }

    div[data-testid="stSelectbox"] svg,
    div[data-testid="stDateInput"] svg,
    div[data-testid="stPasswordInput"] button svg {
        fill: #000000 !important;
        color: #000000 !important;
    }

    /* 3. ESTILIZAÇÃO DO COMPONENTE DE UPLOAD DE ARQUIVOS */
    div[data-testid="stFileUploader"] > section {
        background-color: #FFFFFF !important;
        border: 2px dashed var(--inplanet-green) !important;
        border-radius: 8px !important;
    }
    div[data-testid="stFileUploader"] section div,
    div[data-testid="stFileUploader"] section span {
        color: #000000 !important;
        -webkit-text-fill-color: #000000 !important;
    }
    div[data-testid="stFileUploader"] section button {
        background-color: var(--inplanet-green) !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
    }
    div[data-testid="stFileUploader"] section button * {
        color: #FFFFFF !important;
        fill: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
    }

    /* 4. BOTÕES DE SUBMIT DOS FORMULÁRIOS (DESTACADOS EM VERDE) */
    .stButton > button,
    div[data-testid="stFormSubmitButton"] > button {
        background-color: var(--inplanet-green) !important;
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 0.6rem 1rem !important;
    }
    .stButton > button:hover,
    div[data-testid="stFormSubmitButton"] > button:hover {
        background-color: #487F63 !important;
    }

    /* Rótulos dos Campos (Labels) */
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
        st.info(f"📧 Notificação enviada para: {destinatario}")
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
            st.sidebar.image(img, caption="Mascote Lab Master 🧪", use_container_width=True)
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
    st.stop()

# --- BARRA LATERAL ---
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

menus_disponiveis = ["Dashboard & Inventário", "🛡️ Modo Auditoria (ISO 17025)", "Prontuário & Tendências"]
if st.session_state["user_perfil"] in ["Admin", "Tecnico"]:
    menus_disponiveis.extend(["Gerenciar Equipamentos", "Calibrações & Qualificações", "Manutenções & Intervenções"])
if st.session_state["user_perfil"] == "Admin":
    menus_disponiveis.append("Gestão de Acessos")

menu = st.sidebar.radio("Navegação", menus_disponiveis, index=0)
user_email = st.session_state["user_email"]

st.title("🧪 Lab Master - Gestão de Equipamentos")

# 1. DASHBOARD & INVENTÁRIO
if menu == "Dashboard & Inventário":
    st.header("📌 Inventário Geral e Status Operacional")
    res = supabase.table("equipamentos").select("*").execute()
    df = pd.DataFrame(res.data) if res.data else pd.DataFrame()
    
    if not df.empty:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", len(df))
        c2.metric("Operacionais", len(df[df["status"] == "Operacional"]))
        c3.metric("Em Calibração", len(df[df["status"] == "Em Calibração"]))
        c4.metric("Interditados/Manutenção", len(df[~df["status"].isin(["Operacional", "Em Calibração"])]))
        
        cols_exibir = [c for c in ["tag", "nome", "marca", "modelo", "serial_number", "status", "modalidade_calibracao", "registrado_por"] if c in df.columns]
        st.dataframe(df[cols_exibir], use_container_width=True)

        st.divider()
        st.subheader("🗓️ Planejamento Logístico de Envio (30, 60 e 90 dias)")
        
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
            m2.metric("⚠️ Médio Prazo (31-60 dias)", f"{len(df_60)} eq.")
            m3.metric("✈️ Longo Prazo (61-90 dias)", f"{len(df_90)} eq.")

            t30, t60, t90 = st.tabs(["🔴 Até 30 dias", "🟡 31 a 60 dias", "🔵 61 a 90 dias"])
            cols_v = [c for c in ['equip_tag', 'nome', 'marca', 'modalidade_calibracao', 'data_venc', 'dias_restantes', 'status'] if c in df_calib.columns]

            with t30: st.dataframe(df_30[cols_v] if not df_30.empty else pd.DataFrame(), use_container_width=True)
            with t60: st.dataframe(df_60[cols_v] if not df_60.empty else pd.DataFrame(), use_container_width=True)
            with t90: st.dataframe(df_90[cols_v] if not df_90.empty else pd.DataFrame(), use_container_width=True)
    else:
        st.info("Nenhum equipamento cadastrado.")

# 2. MODO AUDITORIA (ISO 17025)
elif menu == "🛡️ Modo Auditoria (ISO 17025)":
    st.header("🛡️ Visão de Conformidade Metrológica - Auditoria")
    st.caption("Relatório executivo consolidado com o status atual dos equipamentos e acesso à documentação vigente.")
    
    res_eq = supabase.table("equipamentos").select("*").execute()
    df_eq = pd.DataFrame(res_eq.data or [])
    
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
            st.info("Nenhuma calibração cadastrada no sistema.")
    else:
        st.info("Nenhum equipamento cadastrado.")

# 3. PRONTUÁRIO & TENDÊNCIAS
elif menu == "Prontuário & Tendências":
    st.header("📈 Prontuário do Equipamento e Análise de Tendências")
    eq_res = supabase.table("equipamentos").select("tag, nome").execute()
    
    if eq_res.data:
        opcoes_eq = {f"{i['tag']} - {i['nome']}": i['tag'] for i in eq_res.data}
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
        
        st.subheader("🔍 Diagnóstico da Gestão de Riscos")
        if tot_corretivas >= 2:
            st.error(f"🚨 **Alerta de Falha Crônica:** Este equipamento acumulou {tot_corretivas} manutenções corretivas. Recomenda-se abrir uma Investigação de Causa Raiz / Ação Corretiva.")
        elif tot_corretivas == 1:
            st.warning("⚠️ **Atenção:** Equipamento possui 1 registro de manutenção corretiva. Monitore as próximas intervenções.")
        else:
            st.success("✅ **Baixa taxa de falha:** Nenhuma manutenção corretiva crítica até o momento.")
            
        if tot_reprovacoes > 0:
            st.error(f"🚨 **Histórico de Deriva Metrológica:** O equipamento possui {tot_reprovacoes} calibração(ões) reprovada(s). Avalie os ensaios realizados no período correspondente.")

        st.subheader("📜 Linha do Tempo Histórica Unificada")
        eventos = []
        if not df_c.empty:
            for _, r in df_c.iterrows():
                eventos.append({
                    "Data": r.get("data_calib"),
                    "Categoria": "Calibração",
                    "Detalhe / Status": f"Resultado: {r.get('resultado')} (Cert: {r.get('certificado', 'N/A')})",
                    "Registrado por": r.get("registrado_por")
                })
        if not df_m.empty:
            for _, r in df_m.iterrows():
                eventos.append({
                    "Data": r.get("data_intervencao"),
                    "Categoria": "Manutenção",
                    "Detalhe / Status": f"Tipo: {r.get('tipo')} | Descrição: {r.get('descricao')}",
                    "Registrado por": r.get("registrado_por")
                })
                
        df_timeline = pd.DataFrame(eventos)
        if not df_timeline.empty:
            df_timeline['Data_DT'] = pd.to_datetime(df_timeline['Data'])
            df_timeline = df_timeline.sort_values('Data_DT', ascending=False)
            st.dataframe(df_timeline[["Data", "Categoria", "Detalhe / Status", "Registrado por"]], use_container_width=True)
        else:
            st.info("Nenhuma calibração ou manutenção registrada para este equipamento ainda.")
    else:
        st.info("Nenhum equipamento cadastrado.")

# 4. GERENCIAR EQUIPAMENTOS
elif menu == "Gerenciar Equipamentos":
    st.header("📝 Gestão de Equipamentos (Req. 6.4.13)")
    df_eq_exist = pd.DataFrame(supabase.table("equipamentos").select("*").execute().data or [])
    
    abas = ["📝 Cadastrar / Editar", "📁 Importação em Massa"] + (["🗑️ Excluir"] if st.session_state["user_perfil"] == "Admin" else [])
    tabs = st.tabs(abas)
    
    with tabs[0]:
        tags = ["-- Cadastrar Novo --"] + (df_eq_exist["tag"].tolist() if not df_eq_exist.empty else [])
        tag_sel = st.selectbox("Selecione para EDITAR ou mantenha para NOVO:", tags)
        
        def_v = {"tag": "", "nome": "", "marca": "", "modelo": "", "serial_number": "", "status": "Operacional", "modalidade_calibracao": "Envio Externo"}
        if tag_sel != "-- Cadastrar Novo --" and not df_eq_exist.empty:
            def_v = df_eq_exist[df_eq_exist["tag"] == tag_sel].iloc[0].to_dict()
            
        with st.form("form_equip"):
            c1, c2 = st.columns(2)
            with c1:
                tag = st.text_input("Tag / Código Interno", value=str(def_v.get("tag", "")))
                nome = st.text_input("Nome do Equipamento", value=str(def_v.get("nome", "")))
                marca = st.text_input("Marca / Fabricante", value=str(def_v.get("marca", "")))
                op_mod = ["Envio Externo", "In-Loco", "Qualificação OQ/PQ"]
                modalidade = st.selectbox("Modalidade de Serviço", op_mod, index=op_mod.index(def_v.get("modalidade_calibracao", "Envio Externo")) if def_v.get("modalidade_calibracao") in op_mod else 0)
            with c2:
                modelo = st.text_input("Modelo", value=str(def_v.get("modelo", "")))
                serial_number = st.text_input("Número de Série", value=str(def_v.get("serial_number", "")))
                op_st = ["Operacional", "Em Calibração", "Em Manutenção", "Interditado / Fora de Uso"]
                status = st.selectbox("Status Operacional", op_st, index=op_st.index(def_v.get("status", "Operacional")) if def_v.get("status") in op_st else 0)
            
            if st.form_submit_button("Salvar Equipamento"):
                if tag and nome:
                    dado = {"tag": tag, "nome": nome, "marca": marca, "modelo": modelo, "serial_number": serial_number, "status": status, "modalidade_calibracao": modalidade, "registrado_por": user_email}
                    supabase.table("equipamentos").upsert(dado, on_conflict="tag").execute()
                    st.success(f"Equipamento {tag} gravado!")
                    st.rerun()

    with tabs[1]:
        arquivo = st.file_uploader("Suba uma planilha (.csv ou .xlsx)", type=["csv", "xlsx"])
        if arquivo:
            try:
                df_imp = pd.read_csv(arquivo) if arquivo.name.endswith(".csv") else pd.read_excel(arquivo)
                st.dataframe(df_imp.head(), use_container_width=True)
                if st.button("🚀 Confirmar Importação") and "tag" in df_imp.columns and "nome" in df_imp.columns:
                    registros = [{
                        "tag": str(r["tag"]).strip(), "nome": str(r["nome"]).strip(),
                        "marca": str(r.get("marca", "")), "modelo": str(r.get("modelo", "")),
                        "serial_number": str(r.get("serial_number", "")), "status": str(r.get("status", "Operacional")),
                        "modalidade_calibracao": str(r.get("modalidade_calibracao", "Envio Externo")), "registrado_por": user_email
                    } for _, r in df_imp.iterrows()]
                    supabase.table("equipamentos").upsert(registros, on_conflict="tag").execute()
                    st.success("Importado com sucesso!")
                    st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")

    if st.session_state["user_perfil"] == "Admin" and len(tabs) > 2:
        with tabs[2]:
            if not df_eq_exist.empty:
                tag_exc = st.selectbox("Selecione a TAG:", df_eq_exist["tag"].tolist())
                if st.button("🗑️ Excluir Permanentemente") and st.checkbox("Confirmo a exclusão"):
                    supabase.table("equipamentos").delete().eq("tag", tag_exc).execute()
                    st.success("Excluído!")
                    st.rerun()

# 5. CALIBRAÇÕES
elif menu == "Calibrações & Qualificações":
    st.header("📐 Registro de Calibração")
    eq_res = supabase.table("equipamentos").select("tag").execute()
    tags = [i["tag"] for i in eq_res.data] if eq_res.data else []
    lista_gestores = obter_lista_gestores()
    
    if tags:
        with st.form("form_calib", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                equip_tag = st.selectbox("Equipamento *", tags)
                data_calib = st.date_input("Data da Calibração")
                resultado = st.selectbox("Resultado *", ["Aprovado", "Reprovado"])
            with c2:
                data_venc = st.date_input("Próximo Vencimento")
                certificado = st.text_input("Número do Certificado")
                gestor_notificar = st.selectbox("Gestor a Notificar *", lista_gestores)
                
            pdf_file = st.file_uploader("Anexar Certificado (PDF)", type=["pdf"])
            
            if st.form_submit_button("Registrar Calibração"):
                pdf_url = upload_pdf(pdf_file, f"CALIB_{equip_tag}") if pdf_file else None
                supabase.table("calibracoes").insert({"equip_tag": equip_tag, "data_calib": str(data_calib), "data_venc": str(data_venc), "resultado": resultado, "certificado": certificado, "pdf_url": pdf_url, "registrado_por": user_email}).execute()
                
                novo_status = "Operacional" if resultado == "Aprovado" else "Interditado / Fora de Uso"
                supabase.table("equipamentos").update({"status": novo_status}).eq("tag", equip_tag).execute()
                
                if resultado == "Reprovado":
                    enviar_notificacao_email(gestor_notificar, f"🚨 Reprovação de Calibração: {equip_tag}", f"Atenção Gestor,\n\nO equipamento {equip_tag} foi REPROVADO na calibração.\n\nCertificado: {certificado}\nRegistrado por: {user_email}")
                st.success(f"Calibração registrada! Status atualizado para '{novo_status}'.")
                st.rerun()

# 6. MANUTENÇÕES
elif menu == "Manutenções & Intervenções":
    st.header("🛠️ Registro de Manutenção")
    eq_res = supabase.table("equipamentos").select("tag").execute()
    tags = [i["tag"] for i in eq_res.data] if eq_res.data else []
    lista_gestores = obter_lista_gestores()
    
    if tags:
        with st.form("form_manut", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                equip_tag = st.selectbox("Equipamento *", tags)
                tipo = st.selectbox("Tipo de Intervenção *", ["Preventiva", "Corretiva", "Ajuste / Qualificação"])
                data_intervencao = st.date_input("Data")
                tecnico = st.text_input("Técnico / Empresa Responsável")
            with c2:
                status_pos = st.selectbox("Status Pós-Manutenção *", ["Operacional", "Em Calibração", "Em Manutenção", "Interditado / Fora de Uso"])
                gestor_notificar = st.selectbox("Gestor a Notificar *", lista_gestores)
                descricao = st.text_area("Descrição detalhada")
                
            pdf_file = st.file_uploader("Anexar Relatório (PDF)", type=["pdf"])
            
            if st.form_submit_button("Registrar Manutenção"):
                pdf_url = upload_pdf(pdf_file, f"MANUT_{equip_tag}") if pdf_file else None
                supabase.table("manutencoes").insert({"equip_tag": equip_tag, "tipo": tipo, "data_intervencao": str(data_intervencao), "tecnico": tecnico, "descricao": descricao, "pdf_url": pdf_url, "registrado_por": user_email}).execute()
                supabase.table("equipamentos").update({"status": status_pos}).eq("tag", equip_tag).execute()
                
                if tipo == "Corretiva" or status_pos in ["Interditado / Fora de Uso", "Em Manutenção"]:
                    enviar_notificacao_email(gestor_notificar, f"⚠️ Alerta de Manutenção: {equip_tag}", f"Prezado Gestor,\n\nIntervenção registrada para {equip_tag}.\n\nTipo: {tipo}\nNovo Status: {status_pos}\nDescrição: {descricao}\n\nRegistrado por: {user_email}")
                st.success("Manutenção registrada com sucesso!")
                st.rerun()

# 7. GESTÃO DE ACESSOS & ALERTAS
elif menu == "Gestão de Acessos":
    st.header("👥 Gestão de Usuários e Destinatários de Alertas")
    tab_users, tab_alertas = st.tabs(["👤 Controle de Usuários", "📩 Destinatários de Alertas"])
    
    with tab_users:
        st.subheader("Usuários Ativos")
        res_users = supabase.table("usuarios").select("id, email, perfil, criado_em").execute()
        if res_users.data: st.dataframe(pd.DataFrame(res_users.data)[["email", "perfil", "criado_em"]], use_container_width=True)
        
        with st.form("form_user", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            novo_email = col1.text_input("E-mail (@inplanet.earth)")
            novo_perfil = col2.selectbox("Perfil", ["Leitura", "Tecnico", "Admin"])
            nova_senha = col3.text_input("Senha", type="password")
            if st.form_submit_button("Salvar Usuário"):
                if novo_email.endswith("@inplanet.earth") and nova_senha:
                    supabase.table("usuarios").upsert({"email": novo_email, "perfil": novo_perfil, "senha": hash_senha(nova_senha)}, on_conflict="email").execute()
                    st.success("Usuário salvo!")
                    st.rerun()
                else:
                    st.error("Preencha um e-mail @inplanet.earth e uma senha válida.")

    with tab_alertas:
        st.subheader("📋 Lista de Gestores e Destinatários")
        try:
            res_dest = supabase.table("destinatarios_alertas").select("*").execute()
            df_dest = pd.DataFrame(res_dest.data or [])
            if not df_dest.empty: st.dataframe(df_dest[["email", "ativo", "criado_em"]], use_container_width=True)
            
            with st.form("form_destinatario", clear_on_submit=True):
                c1, c2 = st.columns([2, 1])
                email_alerta = c1.text_input("E-mail do Destinatário")
                status_alerta = c2.selectbox("Status", [True, False], format_func=lambda x: "Ativo" if x else "Inativo")
                if st.form_submit_button("Salvar Destinatário") and email_alerta:
                    supabase.table("destinatarios_alertas").upsert({"email": email_alerta, "ativo": status_alerta}, on_conflict="email").execute()
                    st.success("Destinatário salvo!")
                    st.rerun()
        except Exception:
            st.warning("⚠️ Tabela 'destinatarios_alertas' não encontrada no banco.")
