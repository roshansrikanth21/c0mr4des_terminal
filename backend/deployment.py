"""
Deployment and monitoring scripts for the quant system
"""

import schedule
import time
import json
from datetime import datetime, timedelta
from backend.integrated_quant_system import IntegratedQuantSystem
from backend.config import Config
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class QuantSystemDeployer:
    """Deployment manager for the quantitative trading system"""
    
    def __init__(self, email_config=None):
        self.quant_system = IntegratedQuantSystem()
        self.email_config = email_config
        self.last_analysis = None
        
    def daily_analysis_job(self):
        """Run daily comprehensive analysis"""
        print(f"\n[{datetime.now()}] Running daily analysis...")
        results = self.quant_system.run_comprehensive_analysis()
        self.last_analysis = datetime.now()
        
        # Save report
        filename = f"{Config.REPORTS_DIR}/daily_{datetime.now().strftime('%Y%m%d')}.json"
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"✅ Report saved to {filename}")
        
        if self.email_config:
            self.send_daily_report(results)
            
        return results
    
    def intraday_monitoring_job(self):
        """Run intraday monitoring"""
        results = self.quant_system.run_intraday_monitoring(interval="15m")
        if results and results.get('alerts'):
             for alert in results['alerts']:
                 if alert.get('urgency') == 'HIGH':
                     self.send_alert_email(alert)
    
    def send_daily_report(self, results):
        """Send email report"""
        if not self.email_config: return
        try:
            msg = MIMEMultipart()
            msg['Subject'] = f"Quant Report - {datetime.now().strftime('%Y-%m-%d')}"
            msg['From'] = self.email_config['from_email']
            msg['To'] = ', '.join(self.email_config['to_emails'])
            
            body = f"Daily Analysis Complete.\nRegime: {results['regime']['primary_regime']}\nTop Signals: {len(results['integrated_signals']['high_confidence_signals'])}"
            msg.attach(MIMEText(body, 'plain'))
            
            with smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port']) as server:
                server.starttls()
                server.login(self.email_config['username'], self.email_config['password'])
                server.send_message(msg)
        except Exception as e:
            print(f"Error sending email: {e}")

    def send_alert_email(self, alert):
        """Send alert email"""
        if not self.email_config: return
        try:
            with smtplib.SMTP(self.email_config['smtp_server'], self.email_config['smtp_port']) as server:
                server.starttls()
                server.login(self.email_config['username'], self.email_config['password'])
                server.sendmail(
                    self.email_config['from_email'], 
                    self.email_config['alert_emails'],
                    f"Subject: ALERT: {alert['type']}\n\n{alert['message']}"
                )
        except Exception as e:
            print(f"Error sending alert: {e}")

    def start_scheduled_jobs(self):
        """Start scheduled monitoring jobs"""
        print("⏰ Starting scheduled monitoring jobs...")
        
        # Daily analysis at 9:30 AM
        schedule.every().day.at("09:30").do(self.daily_analysis_job)
        
        # Intraday monitoring every 15 minutes
        schedule.every(15).minutes.do(self.intraday_monitoring_job)
        
        # Run initial
        self.daily_analysis_job()
        
        while True:
            schedule.run_pending()
            time.sleep(60)
