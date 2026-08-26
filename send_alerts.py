import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pandas as pd
from datetime import datetime
from supabase import create_client

# Conexão com Supabase via Variáveis de Ambiente
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Configuração de E-mail (SMTP)
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")
EMAIL_TO = os.environ.get("EMAIL_TO") # E-mail do Gestor

def verificar_e_enviar():
    # 1. Consulta Equipamentos Interditados ou em Manutenção
    eq_res = supabase.table("equipamentos").select("*").execute()
    df_eq = pd.DataFrame(eq_res.data) if eq_res.data else pd.DataFrame()
    
    fora_de_uso = []
    if not df_eq.empty:
        indisp = df_eq[df_eq["status"] != "Operacional"]
        for _, row in indisp.iterrows():
            fora_de_uso.append(f"<li><b>{row['tag']}</b> ({row['nome']}): Status = <i>{row['status']}</i></li>")

    # 2. Consulta Calibrações Vencidas ou a Vencer (30 dias)
    calib_res = supabase.table("calibracoes").select("equip_tag, data_venc").execute()
    alertas_calib = []
    
    if calib_res.data:
        df_calib = pd.DataFrame(calib_res.data)
        df_calib['data_venc_dt'] = pd.to_datetime(df_calib['data_venc'])
        hoje = pd.Timestamp.now().normalize()
        
        # Pega a calibração mais recente por equipamento
        df_calib = df_calib.sort_values('data_venc_dt', ascending=False).drop_duplicates('equip_tag')
        df_calib['dias'] = (df_calib['data_venc_dt'] - hoje).dt.days
        
        vencendo = df_calib[df_calib['dias'] <= 30]
        for _, row in vencendo.iterrows():
            dias = row['dias']
            data_str = row['data_venc_dt'].strftime('%d/%m/%Y')
            if dias < 0:
                alertas_calib.append(f"<li>🚨 <b>{row['equip_tag']}</b>: CALIBRAÇÃO VENCIDA em {data_str} ({abs(dias)} dias de atraso)</li>")
            else:
                alertas_calib.append(f"<li>⚠️ <b>{row['equip_tag']}</b>: Vence em {dias} dias ({data_str})</li>")

    # Se houver qualquer pendência, envia o e-mail
    if fora_de_uso or alertas_calib:
        html = f"""
        <h2>🧪 Lab Master - Relatório Diário de Alertas</h2>
        <p>Este é um disparo automático sobre o status metrológico dos equipamentos do laboratório InPlanet.</p>
        
        <h3>1. Calibrações Perto do Vencimento ou Vencidas:</h3>
        <ul>{"".join(alertas_calib) if alertas_calib else "<li>Nenhuma calibração crítica.</li>"}</ul>
        
        <h3>2. Equipamentos Indisponíveis (Fora de Uso / Manutenção):</h3>
        <ul>{"".join(fora_de_uso) if fora_de_uso else "<li>Todos os equipamentos estão operacionais.</li>"}</ul>
        
        <br><p><i>Acesse o painel do Lab Master para mais detalhes.</i></p>
        """
        
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "🚨 [Lab Master] Alerta Diário de Equipamentos e Calibrações"
        msg["From"] = EMAIL_USER
        msg["To"] = EMAIL_TO
        msg.attach(MIMEText(html, "html"))

        try:
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, EMAIL_TO.split(","), msg.as_string())
            server.quit()
            print("E-mail de alerta enviado com sucesso!")
        except Exception as e:
            print(f"Erro ao enviar e-mail: {e}")
    else:
        print("Tudo em dia! Nenhum e-mail disparado hoje.")

if __name__ == "__main__":
    verificar_e_enviar()
