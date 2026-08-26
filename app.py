import streamlit as st
from supabase import create_client, Client

st.set_page_config(page_title="Lab Master - InPlanet", layout="wide")

@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

try:
    supabase: Client = init_connection()
except Exception as e:
    st.error("Erro na conexão com o banco de dados. Verifique os Segredos (Secrets).")
    st.stop()

st.title("🧪 Lab Master - InPlanet")
st.success("✅ Conexão com o Supabase estabelecida com sucesso!")

with st.form("form_teste", clear_on_submit=True):
    st.subheader("Cadastro / Atualização de Equipamento")
    tag = st.text_input("Tag do Equipamento (Ex: EQ-ICP-01)")
    nome = st.text_input("Nome (Ex: Espectrômetro ICP-OES)")
    submit = st.form_submit_button("Salvar no Banco Nuvem")
    
    if submit:
        if tag and nome:
            novo_dado = {"tag": tag, "nome": nome, "status": "Operacional", "registrado_por": "teste@inplanet.earth"}
            try:
                # upsert grava um novo ou atualiza se a TAG já existir
                supabase.table("equipamentos").upsert(novo_dado, on_conflict="tag").execute()
                st.success(f"Equipamento {tag} gravado com sucesso!")
            except Exception as e:
                st.error("Erro ao salvar no banco. Verifique se a TAG é válida.")
        else:
            st.warning("Preencha a Tag e o Nome.")

st.subheader("Equipamentos Registrados")
res = supabase.table("equipamentos").select("*").execute()
if res.data:
    st.dataframe(res.data, use_container_width=True)
else:
    st.info("Nenhum equipamento cadastrado até o momento.")
