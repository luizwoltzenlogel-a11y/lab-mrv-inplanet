import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime

st.set_page_config(page_title="Lab Master - InPlanet", layout="wide")

@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase: Client = init_connection()

# --- TRAVA DE SEGURANÇA E LOGIN CORPORATIVO ---
st.sidebar.title("🔐 Acesso Corporativo")
if "user_email" not in st.session_state:
    st.session_state["user_email"] = ""

user_email = st.sidebar.text_input("E-mail institucional:", value=st.session_state["user_email"], placeholder="seu.nome@inplanet.earth")

if user_email:
    if not user_email.endswith("@inplanet.earth"):
        st.sidebar.error("❌ Acesso restrito a e-mails @inplanet.earth")
        st.stop()
    else:
        st.session_state["user_email"] = user_email
        st.sidebar.success(f"Autenticado: {user_email}")
else:
    st.info("👋 Informe seu e-mail corporativo na barra lateral para liberar as funcionalidades de escrita.")

# Função Auxiliar para Upload de PDFs no Supabase Storage
def upload_pdf(file, prefixo):
    try:
        timestamp = int(datetime.now().timestamp())
        nome_arquivo = f"{prefixo}_{timestamp}_{file.name}"
        conteudo = file.read()
        
        supabase.storage.from_("certificados").upload(
            path=nome_arquivo,
            file=conteudo,
            file_options={"content-type": "application/pdf"}
        )
        return supabase.storage.from_("certificados").get_public_url(nome_arquivo)
    except Exception as e:
        st.error(f"Erro ao salvar o PDF: {e}")
        return None

# --- NAVEGAÇÃO ---
st.title("🧪 Lab Master - Gestão de Equipamentos (ISO 17025)")
menu = st.sidebar.radio("Módulos", ["Dashboard & Inventário", "Cadastrar Equipamento", "Calibrações & Qualificações", "Manutenções & Intervenções"])

# 1. DASHBOARD
if menu == "Dashboard & Inventário":
    st.header("📌 Inventário Geral e Status Operacional")
    res = supabase.table("equipamentos").select("*").execute()
    df = pd.DataFrame(res.data) if res.data else pd.DataFrame()
    
    if not df.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("Total de Equipamentos", len(df))
        col2.metric("Operacionais", len(df[df["status"] == "Operacional"]))
        col3.metric("Interditados / Manutenção", len(df[df["status"] != "Operacional"]))
        
        # Exibe inventário com todos os novos campos
        st.dataframe(df[["tag", "nome", "marca", "modelo", "serial_number", "status", "registrado_por"]], use_container_width=True)

        # --- ALERTAS VISUAIS DE CALIBRAÇÃO ---
        st.subheader("⚠️ Alertas de Calibração (Vencem em até 30 dias)")
        calib_res = supabase.table("calibracoes").select("equip_tag, data_venc, registrado_por").execute()
        
        if calib_res.data:
            df_calib = pd.DataFrame(calib_res.data)
            df_calib['data_venc_dt'] = pd.to_datetime(df_calib['data_venc'])
            hoje = pd.Timestamp.now().normalize()
            
            df_calib = df_calib.sort_values('data_venc_dt', ascending=False).drop_duplicates('equip_tag')
            df_calib['dias'] = (df_calib['data_venc_dt'] - hoje).dt.days
            
            vencendo = df_calib[df_calib['dias'] <= 30]
            
            if not vencendo.empty:
                for _, row in vencendo.iterrows():
                    dias = row['dias']
                    data_str = row['data_venc_dt'].strftime('%d/%m/%Y')
                    status_venc = "VENCIDO!" if dias < 0 else f"Vence em {dias} dias"
                    
                    col_a, col_b = st.columns([5, 1])
                    with col_a:
                        if dias < 0:
                            st.error(f"🚨 **{row['equip_tag']}**: {status_venc} (Limite: {data_str})")
                        else:
                            st.warning(f"⚠️ **{row['equip_tag']}**: {status_venc} (Limite: {data_str})")
                    
                    with col_b:
                        assunto = f"Alerta de Calibracao: {row['equip_tag']}"
                        corpo = f"Olá,%0A%0AA calibração do equipamento {row['equip_tag']} {status_venc.lower()}.%0AData limite: {data_str}.%0A%0AAtenciosamente,%0ALab Master InPlanet"
                        link = f"mailto:{row['registrado_por']}?subject={assunto}&body={corpo}"
                        st.markdown(f'<a href="{link}"><button style="background-color:#4CAF50;color:white;border:none;padding:5px 10px;border-radius:5px;cursor:pointer;">✉️ Notificar</button></a>', unsafe_allow_html=True)
            else:
                st.success("✅ Tudo certo! Nenhuma calibração vence nos próximos 30 dias.")
    else:
        st.info("Nenhum equipamento cadastrado.")

# 2. CADASTRO DE EQUIPAMENTO (COM MARCA, MODELO, SERIAL E IMPORTAÇÃO)
elif menu == "Cadastrar Equipamento":
    st.header("📝 Cadastro e Edição de Equipamentos (Req. 6.4.13)")
    
    tab_ind, tab_massa = st.tabs(["📝 Cadastro Individual", "📁 Importação em Massa (Excel/CSV)"])
    
    with tab_ind:
        with st.form("form_equip", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                tag = st.text_input("Tag / Código Interno (Ex: EQ-ICP-01)")
                nome = st.text_input("Nome do Equipamento")
                marca = st.text_input("Marca / Fabricante")
            with col2:
                modelo = st.text_input("Modelo")
                serial_number = st.text_input("Número de Série (Serial Number)")
                status = st.selectbox("Status Operacional", ["Operacional", "Em Manutenção", "Interditado / Fora de Uso"])
            
            if st.form_submit_button("Salvar Equipamento"):
                if user_email and tag and nome:
                    dado = {
                        "tag": tag, 
                        "nome": nome, 
                        "marca": marca,
                        "modelo": modelo,
                        "serial_number": serial_number,
                        "status": status, 
                        "registrado_por": user_email
                    }
                    supabase.table("equipamentos").upsert(dado, on_conflict="tag").execute()
                    st.success(f"Equipamento {tag} salvo com rastreabilidade!")
                    st.rerun()
                else:
                    st.error("Informe seu e-mail corporativo e preencha a Tag e o Nome.")
                    
    with tab_massa:
        st.markdown("Suba uma planilha **.csv** ou **.xlsx** para cadastrar vários equipamentos de uma só vez.")
        st.caption("Colunas aceitas: `tag`, `nome`, `marca`, `modelo`, `serial_number`, `status`.")
        
        arquivo = st.file_uploader("Selecione o arquivo de inventário", type=["csv", "xlsx"])
        if arquivo:
            try:
                df_import = pd.read_csv(arquivo) if arquivo.name.endswith(".csv") else pd.read_excel(arquivo)
                st.write("Pré-visualização dos dados encontrados:")
                st.dataframe(df_import.head(), use_container_width=True)
                
                if st.button("🚀 Confirmar Importação em Massa"):
                    if not user_email:
                        st.error("Informe seu e-mail corporativo na barra lateral antes de importar.")
                    elif "tag" not in df_import.columns or "nome" not in df_import.columns:
                        st.error("O arquivo precisa conter ao menos as colunas: 'tag' e 'nome'.")
                    else:
                        registros = []
                        for _, row in df_import.iterrows():
                            registros.append({
                                "tag": str(row["tag"]).strip(),
                                "nome": str(row["nome"]).strip(),
                                "marca": str(row["marca"]).strip() if "marca" in df_import.columns and pd.notna(row["marca"]) else None,
                                "modelo": str(row["modelo"]).strip() if "modelo" in df_import.columns and pd.notna(row["modelo"]) else None,
                                "serial_number": str(row["serial_number"]).strip() if "serial_number" in df_import.columns and pd.notna(row["serial_number"]) else None,
                                "status": str(row["status"]).strip() if "status" in df_import.columns and pd.notna(row["status"]) else "Operacional",
                                "registrado_por": user_email
                            })
                        
                        supabase.table("equipamentos").upsert(registros, on_conflict="tag").execute()
                        st.success(f"🎉 {len(registros)} equipamentos importados/atualizados com sucesso!")
                        st.rerun()
            except Exception as e:
                st.error(f"Erro ao ler o arquivo: {e}")

# 3. CALIBRAÇÕES (COM ANEXO DE PDF)
elif menu == "Calibrações & Qualificações":
    st.header("📐 Registro de Calibração / Qualificação (Req. 6.4.6)")
    eq_res = supabase.table("equipamentos").select("tag, nome").execute()
    tags = [item["tag"] for item in eq_res.data] if eq_res.data else []
    
    if tags:
        with st.form("form_calib", clear_on_submit=True):
            equip_tag = st.selectbox("Selecione o Equipamento", tags)
            data_calib = st.date_input("Data da Calibração")
            data_venc = st.date_input("Data do Próximo Vencimento")
            resultado = st.selectbox("Avaliação Metrológica", ["Aprovado", "Reprovado"])
            certificado = st.text_input("Número do Certificado / Laudo")
            pdf_file = st.file_uploader("Anexar Certificado de Calibração (PDF)", type=["pdf"])
            
            if st.form_submit_button("Registrar Calibração"):
                if user_email:
                    pdf_url = upload_pdf(pdf_file, f"CALIB_{equip_tag}") if pdf_file else None
                    
                    dado = {
                        "equip_tag": equip_tag,
                        "data_calib": str(data_calib),
                        "data_venc": str(data_venc),
                        "resultado": resultado,
                        "certificado": certificado,
                        "pdf_url": pdf_url,
                        "registrado_por": user_email
                    }
                    supabase.table("calibracoes").insert(dado).execute()
                    
                    if resultado == "Reprovado":
                        supabase.table("equipamentos").update({"status": "Interditado / Fora de Uso"}).eq("tag", equip_tag).execute()
                        st.warning(f"Equipamento {equip_tag} interditado automaticamente por reprovação!")
                    else:
                        st.success("Calibração e documento registrados com sucesso!")
                    st.rerun()
                else:
                    st.error("Insira o e-mail corporativo.")
        
        st.subheader("Histórico de Calibrações")
        calib_res = supabase.table("calibracoes").select("*").execute()
        if calib_res.data:
            df_calib_show = pd.DataFrame(calib_res.data)
            st.dataframe(
                df_calib_show,
                column_config={"pdf_url": st.column_config.LinkColumn("Certificado PDF", display_text="📎 Visualizar PDF")},
                use_container_width=True
            )
    else:
        st.info("Cadastre um equipamento antes de registrar calibrações.")

# 4. MANUTENÇÕES (COM ANEXO DE PDF)
elif menu == "Manutenções & Intervenções":
    st.header("🛠️ Registro de Manutenção (Req. 6.4.9)")
    eq_res = supabase.table("equipamentos").select("tag, nome").execute()
    tags = [item["tag"] for item in eq_res.data] if eq_res.data else []
    
    if tags:
        with st.form("form_manut", clear_on_submit=True):
            equip_tag = st.selectbox("Selecione o Equipamento", tags)
            tipo = st.selectbox("Tipo de Intervenção", ["Preventiva", "Corretiva", "Ajuste / Qualificação"])
            data_intervencao = st.date_input("Data da Intervenção")
            tecnico = st.text_input("Técnico / Empresa Responsável")
            descricao = st.text_area("Descrição dos Serviços Realizados")
            status_pos = st.selectbox("Status do Equipamento Pós-Manutenção", ["Operacional", "Em Manutenção", "Interditado / Aguardando Calibração"])
            pdf_file = st.file_uploader("Anexar Relatório / Ordem de Serviço (PDF)", type=["pdf"])
            
            if st.form_submit_button("Registrar Manutenção"):
                if user_email:
                    pdf_url = upload_pdf(pdf_file, f"MANUT_{equip_tag}") if pdf_file else None
                    
                    dado = {
                        "equip_tag": equip_tag,
                        "tipo": tipo,
                        "data_intervencao": str(data_intervencao),
                        "tecnico": tecnico,
                        "descricao": descricao,
                        "pdf_url": pdf_url,
                        "registrado_por": user_email
                    }
                    supabase.table("manutencoes").insert(dado).execute()
                    supabase.table("equipamentos").update({"status": status_pos}).eq("tag", equip_tag).execute()
                    st.success("Registro de manutenção e relatório salvos com sucesso!")
                    st.rerun()
                else:
                    st.error("Insira o e-mail corporativo.")
                    
        st.subheader("Histórico de Intervenções")
        manut_res = supabase.table("manutencoes").select("*").execute()
        if manut_res.data:
            df_manut_show = pd.DataFrame(manut_res.data)
            st.dataframe(
                df_manut_show,
                column_config={"pdf_url": st.column_config.LinkColumn("Relatório PDF", display_text="📎 Visualizar PDF")},
                use_container_width=True
            )
    else:
        st.info("Cadastre um equipamento primeiro.")
