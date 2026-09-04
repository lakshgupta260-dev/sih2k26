import os
import httpx
import sys

from app.core.config import settings

def send_template(phone: str, project_name: str, activity_update: str, status: str):
    access_token = settings.META_ACCESS_TOKEN
    phone_id = settings.META_PHONE_NUMBER_ID
    
    url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": phone,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": f"*Plan2Progress Report*\n\nProject: {project_name}\nActivity Update: {activity_update}\nStatus: {status}\n\nYour progress report has been successfully logged into the database. What would you like to do next?"
            },
            "action": {
                "buttons": [
                    {
                        "type": "reply",
                        "reply": {
                            "id": "view_report",
                            "title": "View Dashboard"
                        }
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "delay_report",
                            "title": "Delay Report"
                        }
                    },
                    {
                        "type": "reply",
                        "reply": {
                            "id": "call_ai",
                            "title": "Call AI Assistant"
                        }
                    }
                ]
            }
        }
    }

    with httpx.Client() as client:
        response = client.post(url, json=payload, headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        phone = sys.argv[1]
    else:
        phone = "919625433606"
        
    send_template(
        phone, 
        project_name="Plan2Progress Demo", 
        activity_update="Concrete Pouring", 
        status="Completed 50 units"
    )
