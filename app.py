import re
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
from supabase import create_client, Client

# 1. Configuração de Página e Estilo
st.set_page_config(
    page_title="Lab Master ISO 17025 - InPlanet",
    page_icon="🧪",
    layout="wide"
)

st.markdown("""
    <style>
    :root {
        --inplanet-dark: #121512;
        --inplanet-card: #1A201B;
        --inplanet-green: #3A6B52;
    }
    .stApp { background-color: var(--inplanet-dark) !important; }
    div[data-testid="stMetricValue"] { color: #FFFFFF !important; font-weight: 700; }
    .stButton > button {
        background-color: var(--inplanet-green) !important;
        color: #FFFFFF !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
    }
    </style>
""", unsafe_allow_html=True)

# 2. Inicialização Resiliente do Supabase
@st.cache_resource
def init_supabase() -> Client:
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"❌ Erro ao conectar ao Supabase. Verifique os secrets: {e}")
        st.stop()

supabase = init_supabase()

# 3. Gerenciamento de Sessão e Autenticação
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
    st.session_state["user_email"] = ""
    st.session_state["user_role"] = "VIEWER"

# --- TELA DE AUTENTICAÇÃO ---
if not st.session_state["autenticado"]:
    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.title("🧪 Lab Master LMS")
        st.caption("Acesso Restrito - Controle Metrológico ISO/IEC 17025")
        
        with st.form("form_login"):
            email_input = st.text_input("E-mail Institucional (@inplanet.earth)")
            role_input = st.selectbox("Perfil de Acesso (Simulação SSO)", ["OPERATOR", "QUALITY_MANAGER", "VIEWER"])
            
            if st.form_submit_button("Entrar no Sistema", use_container_width=True):
                email_clean = email_input.strip().lower()
                if not email_clean.endswith("@inplanet.earth"):
                    st.error("❌ Acesso negado: O e-mail deve obrigatoriamente pertencer ao domínio @inplanet.earth")
                else:
                    st.session_state["autenticado"] = True
                    st.session_state["user_email"] = email_clean
                    st.session_state["user_role"] = role_input
                    st.success("Autenticado com sucesso!")
                    st.rerun()
    st.stop()

# --- BARRA LATERAL E NAVEGAÇÃO ---
st.sidebar.title("🔬 Lab Master 17025")
st.sidebar.write(f"👤 **Usuário:** {st.session_state['user_email']}")
st.sidebar.write(f"🛡️ **Perfil:** {st.session_state['user_role']}")

if st.sidebar.button("🚪 Sair"):
    st.session_state["autenticado"] = False
    st.rerun()

st.sidebar.divider()

menu = st.sidebar.radio(
    "Módulos Normativos",
    [
        "📌 Inventário & Status (6.4)",
        "🧪 Admissão ('Estado Zero') (6.4.4)",
        "📐 Calibração & Metrologia (6.5)",
        "🚨 Ocorrências & Seção 7.10",
        "📝 Gerenciar Equipamentos (6.4.13)"
    ]
)

# ==============================================================================
# MÓDULO 1: INVENTÁRIO E STATUS OPERACIONAL (ITEM 6.4)
# ==============================================================================
if menu == "📌 Inventário & Status (6.4)":
    st.header("📌 Inventário de Equipamentos e Status Operacional")
    
    try:
        res = supabase.table("equipments").select("*").eq("is_deleted", False).execute()
        df = pd.DataFrame(res.data or [])
        
        if not df.empty:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total de Ativos", len(df))
            c2.metric("Operacionais", len(df[df["status"] == "OPERATIONAL"]))
            c3.metric("Em Quarentena / Falha", len(df[df["status"] == "QUARANTINE_OUT_OF_SERVICE"]))
            c4.metric("Bloqueados / Vencidos", len(df[df["status"] == "BLOCKED_EXPIRED"]))
            
            st.divider()
            st.dataframe(
                df[[
                    "code_tag", "name", "manufacturer", "model", 
                    "serial_number", "location", "status", 
                    "next_calibration_due", "next_maintenance_due"
                ]],
                use_container_width=True
            )
        else:
            st.info("Nenhum equipamento ativo cadastrado no sistema.")
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")

# ==============================================================================
# MÓDULO 2: ADMISSÃO DE EQUIPAMENTOS NOVOS ("ESTADO ZERO")
# ==============================================================================
elif menu == "🧪 Admissão ('Estado Zero') (6.4.4)":
    st.header("🧪 Comissionamento e Liberação de Equipamentos Novos")
    st.caption("Equipamentos recém-cadastrados permanecem bloqueados para ensaios até a aprovação técnica inicial.")
    
    try:
        res = supabase.table("equipments").select("*").eq("status", "COMMISSIONING").eq("is_deleted", False).execute()
        df_comm = pd.DataFrame(res.data or [])
        
        if not df_comm.empty:
            st.subheader("Equipamentos em Fase de Implantação")
            st.dataframe(df_comm[["code_tag", "name", "manufacturer", "model", "serial_number", "created_at"]], use_container_width=True)
            
            if st.session_state["user_role"] == "QUALITY_MANAGER":
                st.divider()
                st.subheader("Aprovação da Liberação Técnica")
                
                equip_opcoes = {f"{r['code_tag']} - {r['name']}": r['id'] for _, r in df_comm.iterrows()}
                equip_sel = st.selectbox("Selecione o Equipamento:", list(equip_opcoes.keys()))
                equip_id = equip_opcoes[equip_sel]
                
                with st.form("form_liberacao"):
                    emp_val = st.number_input("Erro Máximo Permitido (EMP) do Processo *", min_value=0.000001, format="%.6f")
                    emp_unit = st.text_input("Unidade de Medida (ex: mg, °C) *")
                    param_name = st.text_input("Parâmetro de Medição *", value="Faixa Operacional Principal")
                    
                    if st.form_submit_button("Aprovar Comissionamento e Definir EMP"):
                        # Registra o Critério de Aceitação (EMP)
                        supabase.table("acceptance_criteria").insert({
                            "equipment_id": equip_id,
                            "parameter_name": param_name,
                            "emp_value": float(emp_val),
                            "unit": emp_unit
                        }).execute()
                        
                        st.success("Critério de Aceitação (EMP) cadastrado. Realize o registro do 1º Certificado de Calibração para liberar o equipamento para OPERATIONAL.")
        else:
            st.info("Nenhum equipamento em fase de comissionamento ('Estado Zero').")
    except Exception as e:
        st.error(f"Erro no módulo de admissão: {e}")

# ==============================================================================
# MÓDULO 3: CALIBRAÇÃO E AVALIAÇÃO METROLÓGICA (ITEM 6.5)
# ==============================================================================
elif menu == "📐 Calibração & Metrologia (6.5)":
    st.header("📐 Avaliação Metrológica de Certificados de Calibração")
    
    try:
        res_eq = supabase.table("equipments").select("id, code_tag, name, calibration_period_months").eq("is_deleted", False).execute()
        equipamentos = res_eq.data or []
        
        if equipamentos:
            dict_eq = {f"{e['code_tag']} - {e['name']}": e for e in equipamentos}
            sel_eq_label = st.selectbox("Selecione o Equipamento *", list(dict_eq.keys()))
            selected_eq = dict_eq[sel_eq_label]
            
            # Busca EMP cadastrado
            res_emp = supabase.table("acceptance_criteria").select("*").eq("equipment_id", selected_eq["id"]).eq("is_active", True).execute()
            emp_data = res_emp.data
            
            if not emp_data:
                st.warning("⚠️ Este equipamento não possui um Erro Máximo Permitido (EMP) cadastrado. Configure-o primeiro.")
            else:
                emp_val = float(emp_data[0]["emp_value"])
                unit = emp_data[0]["unit"]
                st.info(f"📏 **Critério de Aceitação Cadastrado (EMP):** ± {emp_val} {unit}")
                
                with st.form("form_calib_metrologia"):
                    c1, c2 = st.columns(2)
                    cert_num = c1.text_input("Número do Certificado / Laudo *")
                    calib_date = c2.date_input("Data da Calibração *", value=datetime.now().date())
                    
                    accredited_body = c1.text_input("Laboratório Calibrador (RBC / ISO 17025) *")
                    traceability = c2.text_input("Código de Rastreabilidade Metrológica (SI/RBC) *")
                    
                    m_error = c1.number_input("Erro Sistemático Medido (|E|) *", format="%.6f")
                    uncertainty = c2.number_input("Incerteza Expandida (U, k=2, 95.45%) *", min_value=0.000000, format="%.6f")
                    
                    if st.form_submit_button("Avaliar Certificado e Gravar"):
                        # Aplicação estrita da Regra de Decisão Metrológica: (|E| + U) <= EMP
                        total_deviation = abs(m_error) + abs(uncertainty)
                        is_conformant = total_deviation <= emp_val
                        
                        # Cálculo da próxima data
                        months = selected_eq["calibration_period_months"]
                        next_due = calib_date + timedelta(days=30 * months)
                        
                        # Inserção do Registro
                        supabase.table("calibration_events").insert({
                            "equipment_id": selected_eq["id"],
                            "certificate_number": cert_num,
                            "calibration_date": str(calib_date),
                            "accredited_body": accredited_body,
                             trace_code: traceability if (trace_code := traceability) else "N/A",
                            "traceability_code": traceability,
                            "measured_error": float(m_error),
                            "expanded_uncertainty": float(uncertainty),
                            "is_conformant": is_conformant,
                            "approved_by_user": st.session_state["user_email"]
                        }).execute()
                        
                        # Atualização de Status do Equipamento
                        new_status = "OPERATIONAL" if is_conformant else "QUARANTINE_OUT_OF_SERVICE"
                        supabase.table("equipments").update({
                            "status": new_status,
                            "next_calibration_due": str(next_due),
                            "updated_at": "NOW()"
                        }).eq("id", selected_eq["id"]).execute()
                        
                        if is_conformant:
                            st.success(f"✅ CERTIFICADO CONFORME! (|E| + U = {total_deviation:.6f} ≤ EMP {emp_val:.6f}). Equipamento LIBERADO.")
                        else:
                            st.error(f"🚨 CERTIFICADO NÃO CONFORME! (|E| + U = {total_deviation:.6f} > EMP {emp_val:.6f}). Equipamento colocado em QUARENTENA.")
                        st.rerun()
    except Exception as e:
        st.error(f"Erro no processamento metrológico: {e}")

# ==============================================================================
# MÓDULO 4: LOGBOOK E TRABALHO NÃO CONFORME (ITEM 7.10)
# ==============================================================================
elif menu == "🚨 Ocorrências & Seção 7.10":
    st.header("🚨 Registro de Ocorrências e Trabalho Não Conforme (7.10)")
    
    tab1, tab2 = st.tabs(["📝 Logbook / Registrar Evento", "🔍 Investigação Retroativa 7.10"])
    
    with tab1:
        res_eq = supabase.table("equipments").select("id, code_tag, name").eq("is_deleted", False).execute()
        eqs = res_eq.data or []
        
        if eqs:
            dict_eq = {f"{e['code_tag']} - {e['name']}": e['id'] for e in eqs}
            sel_label = st.selectbox("Equipamento Relacionado *", list(dict_eq.keys()))
            eq_id = dict_eq[sel_label]
            
            with st.form("form_event_log"):
                ev_type = st.selectbox(
                    "Tipo de Ocorrência *",
                    [
                        ("FALHA / QUEBRA OPERACIONAL", "FAILURE_BREAKDOWN"),
                        ("ENVIO PARA CALIBRAÇÃO EXTERNA", "EXTERNAL_CALIBRATION_SEND"),
                        ("ENVIO PARA MANUTENÇÃO EXTERNA", "EXTERNAL_MAINTENANCE_SEND"),
                        ("MUDANÇA DE LOCALIZAÇÃO", "LOCATION_CHANGE")
                    ],
                    format_func=lambda x: x[0]
                )
                desc = st.text_area("Descrição Detalhada do Evento *")
                
                if st.form_submit_button("Registrar Ocorrência"):
                    supabase.table("equipment_events").insert({
                        "equipment_id": eq_id,
                        "event_type": ev_type[1],
                        "user_email": st.session_state["user_email"],
                        "description": desc
                    }).execute()
                    
                    st.success("Ocorrência gravada no Logbook! Triggers automáticas executadas.")
                    st.rerun()

    with tab2:
        st.subheader("Processos de Trabalho Não Conforme Abertos (Item 7.10)")
        res_nc = supabase.table("non_conforming_work").select("*, equipments(code_tag, name)").eq("status", "UNDER_INVESTIGATION").execute()
        df_nc = pd.DataFrame(res_nc.data or [])
        
        if not df_nc.empty:
            st.dataframe(df_nc[["id", "impact_analysis", "is_halted", "created_at"]], use_container_width=True)
        else:
            st.info("Nenhuma investigação de Trabalho Não Conforme aberta no momento.")

# ==============================================================================
# MÓDULO 5: GERENCIAR EQUIPAMENTOS (SOFT DELETE E EDITIONS)
# ==============================================================================
elif menu == "📝 Gerenciar Equipamentos (6.4.13)":
    st.header("📝 Cadastro e Manutenção de Equipamentos")
    
    if st.session_state["user_role"] in ["QUALITY_MANAGER", "OPERATOR"]:
        with st.form("form_cad_eq"):
            c1, c2 = st.columns(2)
            tag = c1.text_input("Tag do Equipamento (Formato: AAAA-NNN) *", placeholder="BALA-001")
            nome = c2.text_input("Nome / Descrição *")
            
            marca = c1.text_input("Fabricante *")
            modelo = c2.text_input("Modelo *")
            
            serial = c1.text_input("Número de Série *")
            local = c2.text_input("Localização Física / Laboratório *")
            
            cal_months = c1.number_input("Periodicidade de Calibração (Meses) *", min_value=1, value=12)
            maint_months = c2.number_input("Periodicidade de Manutenção (Meses) *", min_value=1, value=12)
            
            if st.form_submit_button("Cadastrar Equipamento ('Estado Zero')"):
                tag_clean = tag.strip().upper()
                if not re.match(r'^[A-Z]{4}-\d{3}$', tag_clean):
                    st.error("❌ A Tag deve seguir estritamente o padrão de 4 letras, hífen e 3 dígitos (Ex: BALA-001).")
                else:
                    supabase.table("equipments").insert({
                        "code_tag": tag_clean,
                        "name": nome,
                        "manufacturer": marca,
                        "model": modelo,
                        "serial_number": serial,
                        "location": local,
                        "calibration_period_months": int(cal_months),
                        "maintenance_period_months": int(maint_months),
                        "status": "COMMISSIONING"
                    }).execute()
                    st.success(f"Equipamento {tag_clean} registrado com sucesso em 'Estado Zero' (COMMISSIONING).")
                    st.rerun()

    # Operação de Soft Delete (Apenas Admin / Gestor da Qualidade)
    if st.session_state["user_role"] == "QUALITY_MANAGER":
        st.divider()
        st.subheader("🗑️ Desativação Lógica de Ativo (Soft Delete)")
        res_del = supabase.table("equipments").select("id, code_tag, name").eq("is_deleted", False).execute()
        eqs_del = res_del.data or []
        
        if eqs_del:
            dict_del = {f"{e['code_tag']} - {e['name']}": e['id'] for e in eqs_del}
            sel_del_label = st.selectbox("Selecione para Desativar:", list(dict_del.keys()))
            
            if st.button("🚫 Marcar como Inativo (Soft Delete)"):
                supabase.table("equipments").update({"is_deleted": True}).eq("id", dict_del[sel_del_label]).execute()
                st.success("Equipamento desativado mantendo todo o histórico imutável para fins de auditoria.")
                st.rerun()
