import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime
import hashlib

st.set_page_config(page_title="Lab Master - InPlanet", layout="wide")

@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase: Client = init_connection()

def hash_senha(senha_plana):
    return hashlib.sha256(senha_plana.encode()).hexdigest()

# --- GESTÃO DE SESSÃO E LOGIN ---
if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
    st.session_state["user_email"] = ""
    st.session_state["user_perfil"] = ""

# TELA DE LOGIN
if not st.session_state["autenticado"]:
    st.title("🔐 Lab Master - Acesso Restrito")
    st.write("Insira suas credenciais para acessar o sistema de gestão metrológica.")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
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

# --- BARRA LATERAL (Usuário Logado) ---
st.sidebar.title("👤 Meu Perfil")
st.sidebar.write(f"**E-mail:** {st.session_state['user_email']}")
st.sidebar.write(f"**Permissão:** {st.session_state['user_perfil']}")

if st.sidebar.button("🚪 Sair do Sistema"):
    st.session_state.clear()
    st.rerun()

st.sidebar.divider()

# --- DEFINIÇÃO DE MENUS POR PERFIL ---
menus_disponiveis = ["Dashboard & Inventário"]
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
        col1, col2, col3 = st.columns(3)
        col1.metric("Total de Equipamentos", len(df))
        col2.metric("Operacionais", len(df[df["status"] == "Operacional"]))
        col3.metric("Interditados / Manutenção", len(df[df["status"] != "Operacional"]))
        
        st.dataframe(df[["tag", "nome", "marca", "modelo", "serial_number", "status", "registrado_por"]], use_container_width=True)

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
                    if dias < 0:
                        st.error(f"🚨 **{row['equip_tag']}**: {status_venc} (Limite: {data_str})")
                    else:
                        st.warning(f"⚠️ **{row['equip_tag']}**: {status_venc} (Limite: {data_str})")
            else:
                st.success("✅ Tudo certo! Nenhuma calibração vence nos próximos 30 dias.")
    else:
        st.info("Nenhum equipamento cadastrado.")

# 2. GERENCIAR EQUIPAMENTOS
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
        
        def_tag, def_nome, def_marca, def_modelo, def_sn, def_status = "", "", "", "", "", "Operacional"
        if tag_selecionada != "-- Cadastrar Novo Equipamento --" and not df_eq_exist.empty:
            row = df_eq_exist[df_eq_exist["tag"] == tag_selecionada].iloc[0]
            def_tag = str(row.get("tag", ""))
            def_nome = str(row.get("nome", ""))
            def_marca = str(row.get("marca", "")) if pd.notna(row.get("marca")) else ""
            def_modelo = str(row.get("modelo", "")) if pd.notna(row.get("modelo")) else ""
            def_sn = str(row.get("serial_number", "")) if pd.notna(row.get("serial_number")) else ""
            def_status = str(row.get("status", "Operacional"))
            
        with st.form("form_equip", clear_on_submit=False):
            col1, col2 = st.columns(2)
            with col1:
                tag = st.text_input("Tag / Código Interno", value=def_tag)
                nome = st.text_input("Nome do Equipamento", value=def_nome)
                marca = st.text_input("Marca / Fabricante", value=def_marca)
            with col2:
                modelo = st.text_input("Modelo", value=def_modelo)
                serial_number = st.text_input("Número de Série", value=def_sn)
                opcoes_status = ["Operacional", "Em Manutenção", "Interditado / Fora de Uso"]
                idx_status = opcoes_status.index(def_status) if def_status in opcoes_status else 0
                status = st.selectbox("Status Operacional", opcoes_status, index=idx_status)
            
            label_btn = "Atualizar Equipamento" if tag_selecionada != "-- Cadastrar Novo Equipamento --" else "Salvar Novo Equipamento"
            if st.form_submit_button(label_btn):
                if tag and nome:
                    dado = {"tag": tag, "nome": nome, "marca": marca, "modelo": modelo, "serial_number": serial_number, "status": status, "registrado_por": user_email}
                    supabase.table("equipamentos").upsert(dado, on_conflict="tag").execute()
                    st.success(f"Equipamento {tag} gravado!")
                    st.rerun()
                else:
                    st.error("Preencha a Tag e o Nome.")

    with tab_massa:
        st.markdown("Suba uma planilha **.csv** ou **.xlsx**.")
        arquivo = st.file_uploader("Selecione o arquivo", type=["csv", "xlsx"])
        if arquivo:
            try:
                df_import = pd.read_csv(arquivo) if arquivo.name.endswith(".csv") else pd.read_excel(arquivo)
                st.dataframe(df_import.head(), use_container_width=True)
                if st.button("🚀 Confirmar Importação"):
                    if "tag" not in df_import.columns or "nome" not in df_import.columns:
                        st.error("O arquivo precisa conter as colunas: 'tag' e 'nome'.")
                    else:
                        registros = []
                        for _, row in df_import.iterrows():
                            registros.append({
                                "tag": str(row["tag"]).strip(), "nome": str(row["nome"]).strip(),
                                "marca": str(row["marca"]).strip() if "marca" in df_import.columns and pd.notna(row["marca"]) else None,
                                "modelo": str(row["modelo"]).strip() if "modelo" in df_import.columns and pd.notna(row["modelo"]) else None,
                                "serial_number": str(row["serial_number"]).strip() if "serial_number" in df_import.columns and pd.notna(row["serial_number"]) else None,
                                "status": str(row["status"]).strip() if "status" in df_import.columns and pd.notna(row["status"]) else "Operacional",
                                "registrado_por": user_email
                            })
                        supabase.table("equipamentos").upsert(registros, on_conflict="tag").execute()
                        st.success("Equipamentos importados com sucesso!")
                        st.rerun()
            except Exception as e:
                st.error(f"Erro: {e}")

    if st.session_state["user_perfil"] == "Admin":
        with tab_exc:
            st.subheader("🗑️ Excluir Registro")
            if not df_eq_exist.empty:
                tag_excluir = st.selectbox("Selecione a TAG:", df_eq_exist["tag"].tolist())
                if st.button("🗑️ Excluir Permanentemente") and st.checkbox("Confirmo a exclusão"):
                    try:
                        supabase.table("equipamentos").delete().eq("tag", tag_excluir).execute()
                        st.success("Excluído com sucesso!")
                        st.rerun()
                    except:
                        st.error("Erro: Remova primeiro as dependências (calibrações/manutenções).")

# 3. CALIBRAÇÕES
elif menu == "Calibrações & Qualificações":
    st.header("📐 Registro de Calibração")
    eq_res = supabase.table("equipamentos").select("tag").execute()
    tags = [item["tag"] for item in eq_res.data] if eq_res.data else []
    
    if tags:
        with st.form("form_calib", clear_on_submit=True):
            equip_tag = st.selectbox("Equipamento", tags)
            data_calib = st.date_input("Data da Calibração")
            data_venc = st.date_input("Próximo Vencimento")
            resultado = st.selectbox("Resultado", ["Aprovado", "Reprovado"])
            certificado = st.text_input("Número do Certificado")
            pdf_file = st.file_uploader("Anexar Certificado (PDF)", type=["pdf"])
            
            if st.form_submit_button("Registrar"):
                pdf_url = upload_pdf(pdf_file, f"CALIB_{equip_tag}") if pdf_file else None
                dado = {"equip_tag": equip_tag, "data_calib": str(data_calib), "data_venc": str(data_venc), "resultado": resultado, "certificado": certificado, "pdf_url": pdf_url, "registrado_por": user_email}
                supabase.table("calibracoes").insert(dado).execute()
                if resultado == "Reprovado":
                    supabase.table("equipamentos").update({"status": "Interditado / Fora de Uso"}).eq("tag", equip_tag).execute()
                st.success("Salvo com sucesso!")
                st.rerun()
                
        st.subheader("Histórico")
        calib_res = supabase.table("calibracoes").select("*").execute()
        if calib_res.data:
            st.dataframe(pd.DataFrame(calib_res.data), column_config={"pdf_url": st.column_config.LinkColumn("Certificado PDF")}, use_container_width=True)

# 4. MANUTENÇÕES
elif menu == "Manutenções & Intervenções":
    st.header("🛠️ Registro de Manutenção")
    eq_res = supabase.table("equipamentos").select("tag").execute()
    tags = [item["tag"] for item in eq_res.data] if eq_res.data else []
    
    if tags:
        with st.form("form_manut", clear_on_submit=True):
            equip_tag = st.selectbox("Equipamento", tags)
            tipo = st.selectbox("Tipo", ["Preventiva", "Corretiva", "Ajuste / Qualificação"])
            data_intervencao = st.date_input("Data")
            tecnico = st.text_input("Técnico")
            descricao = st.text_area("Descrição")
            status_pos = st.selectbox("Status Pós-Manutenção", ["Operacional", "Em Manutenção", "Interditado / Aguardando Calibração"])
            pdf_file = st.file_uploader("Anexar Relatório (PDF)", type=["pdf"])
            
            if st.form_submit_button("Registrar"):
                pdf_url = upload_pdf(pdf_file, f"MANUT_{equip_tag}") if pdf_file else None
                dado = {"equip_tag": equip_tag, "tipo": tipo, "data_intervencao": str(data_intervencao), "tecnico": tecnico, "descricao": descricao, "pdf_url": pdf_url, "registrado_por": user_email}
                supabase.table("manutencoes").insert(dado).execute()
                supabase.table("equipamentos").update({"status": status_pos}).eq("tag", equip_tag).execute()
                st.success("Salvo com sucesso!")
                st.rerun()
                    
        st.subheader("Histórico")
        manut_res = supabase.table("manutencoes").select("*").execute()
        if manut_res.data:
            st.dataframe(pd.DataFrame(manut_res.data), column_config={"pdf_url": st.column_config.LinkColumn("Relatório PDF")}, use_container_width=True)

# 5. GESTÃO DE ACESSOS (Apenas Admin)
elif menu == "Gestão de Acessos":
    st.header("👥 Gestão de Usuários e Permissões")
    
    # Listar Usuários
    st.subheader("Usuários Ativos")
    res_users = supabase.table("usuarios").select("id, email, perfil, criado_em").execute()
    if res_users.data:
        df_users = pd.DataFrame(res_users.data)
        st.dataframe(df_users[["email", "perfil", "criado_em"]], use_container_width=True)
    
    st.divider()
    
    # Cadastrar/Editar Usuário
    st.subheader("Cadastrar Novo Usuário ou Atualizar Senha/Perfil")
    with st.form("form_user", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            novo_email = st.text_input("E-mail Institucional (@inplanet.earth)")
        with col2:
            novo_perfil = st.selectbox("Nível de Acesso", ["Leitura", "Tecnico", "Admin"])
        with col3:
            nova_senha = st.text_input("Senha Inicial", type="password")
            
        submit_user = st.form_submit_button("Salvar Usuário")
        if submit_user:
            if novo_email and nova_senha:
                if not novo_email.endswith("@inplanet.earth"):
                    st.error("❌ Apenas e-mails do domínio @inplanet.earth são permitidos.")
                else:
                    senha_hash = hash_senha(nova_senha)
                    dado = {"email": novo_email, "perfil": novo_perfil, "senha": senha_hash}
                    # Upsert: se o email já existir, atualiza perfil e senha.
                    try:
                        supabase.table("usuarios").upsert(dado, on_conflict="email").execute()
                        st.success(f"✅ Usuário {novo_email} salvo com sucesso!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar usuário: {e}")
            else:
                st.error("Preencha E-mail e Senha.")
