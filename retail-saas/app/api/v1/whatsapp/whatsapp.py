from fastapi import APIRouter, HTTPException
from datetime import datetime,timedelta
from enum import Enum
import uuid


router = APIRouter(
    prefix="/api/v1/whatsapp",
    tags=["WhatsApp"]
)



# ============================
# ENUMS
# ============================


class Status(str,Enum):
    ACTIVE="ACTIVE"
    INACTIVE="INACTIVE"


class DeliveryStatus(str,Enum):
    SENT="SENT"
    DELIVERED="DELIVERED"
    READ="READ"
    FAILED="FAILED"



class TemplateStatus(str,Enum):
    PENDING="PENDING"
    APPROVED="APPROVED"
    REJECTED="REJECTED"



# ============================
# TEMP DATABASE STORAGE
# (replace with SQLAlchemy)
# ============================


accounts=[]

templates=[]

messages=[]

campaigns=[]

campaign_users=[]

chats=[]

chat_messages=[]

failed_queue=[]

audit_logs=[]



# ==================================================
# FR-1 WhatsApp Account Configuration
# ==================================================


@router.post("/accounts")
def create_account(data:dict):

    account={

        "id":uuid.uuid4().int,

        "tenant_id":
        data.get("tenant_id"),

        "business_name":
        data.get("business_name"),

        "phone_number":
        data.get("phone_number"),

        "phone_number_id":
        data.get("phone_number_id"),

        "access_token":
        data.get("access_token"),

        "status":"ACTIVE",

        "created_at":datetime.now()

    }


    accounts.append(account)

    return account



@router.get("/accounts")
def get_accounts():

    return accounts



@router.put("/accounts/{id}")
def update_account(id:int,data:dict):

    for a in accounts:

        if a["id"]==id:
            a.update(data)

            return a

    raise HTTPException(404)



# ==================================================
# FR-15 Templates
# ==================================================


@router.post("/templates")
def create_template(data:dict):


    template={

        "id":uuid.uuid4().int,

        "template_name":
        data["template_name"],


        "category":
        data["category"],


        "content":
        data["template_content"],


        "status":
        "PENDING",


        "version":1

    }


    templates.append(template)

    return template




@router.get("/templates")
def templates_list():

    return templates




@router.put("/templates/{id}")
def update_template(id:int,data:dict):

    for t in templates:

        if t["id"]==id:

            t.update(data)

            t["version"]+=1

            return t



# ==================================================
# Message APIs
# ==================================================


@router.post("/sendmessage")
def send_message(data:dict):


    msg={

    "id":uuid.uuid4().int,

    "customer_id":
    data.get("customer_id"),


    "recipient":
    data["phone"],


    "message":
    data["message"],


    "status":
    "SENT",


    "sent_at":
    datetime.now()

    }


    messages.append(msg)


    return msg




@router.post("/send-template")
def send_template(data:dict):


    return send_message({

        "customer_id":
        data["customer_id"],

        "phone":
        data["phone"],

        "message":
        "Template Message"

    })



@router.get("/messages")
def get_messages():

    return messages




# ==================================================
# FR-6 Campaigns
# ==================================================


@router.post("/campaigns")
def create_campaign(data:dict):


    campaign={

    "id":uuid.uuid4().int,

    "campaign_name":
    data["campaign_name"],

    "type":
    data["campaign_type"],


    "segment":
    data["target_segment"],


    "scheduled_at":
    data.get("scheduled_at"),


    "status":
    "CREATED"

    }


    campaigns.append(campaign)

    return campaign



@router.get("/campaigns")
def get_campaigns():

    return campaigns



@router.put("/campaigns/{id}")
def update_campaign(id:int,data:dict):

    for c in campaigns:

        if c["id"]==id:

            c.update(data)

            return c



@router.post("/broadcast")
def broadcast(data:dict):

    return {

    "message":
    "Broadcast started",

    "customers":
    len(data["customers"])

    }



# ==================================================
# FR-10 Chat Support
# ==================================================


@router.get("/chats")
def get_chats():

    return chats




@router.get("/chats/{id}")
def chat_detail(id:int):

    return [
        x for x in chat_messages
        if x["chat_id"]==id
    ]



@router.post("/chats/{id}/reply")
def reply_chat(id:int,data:dict):


    message={

    "chat_id":id,

    "sender":"AGENT",

    "message":
    data["message"],

    "time":
    datetime.now()

    }


    chat_messages.append(message)


    return message



@router.put("/chats/{id}/assign")
def assign_agent(id:int,data:dict):

    return {

    "chat":id,

    "agent":
    data["agent_id"],

    "status":
    "ASSIGNED"

    }




# ==================================================
# Webhooks
# ==================================================


@router.post("/../webhooks/whatsapp")
def whatsapp_webhook(data:dict):


    messages.append({

        "type":"incoming",

        "data":data

    })


    return {
        "received":True
    }




# ==================================================
# FR-13 Abandoned Cart
# ==================================================


@router.post("/cart-reminder")
def abandoned_cart(data:dict):


    return {

    "message":
    "Reminder sent"

    }




# ==================================================
# FR-14 Feedback
# ==================================================


@router.post("/feedback")
def feedback(data:dict):


    return {

    "message":
    "Feedback request sent"

    }




# ==================================================
# FR-17 Retry Mechanism
# ==================================================


@router.post("/retry")


def retry_failed():


    for item in failed_queue:

        item["retry"]+=1


    return {

    "message":
    "Retry completed"

    }




# ==================================================
# Analytics Dashboard
# ==================================================


@router.get("/analytics")
def analytics():


    return {


    "messages_sent":
    len(messages),


    "delivered":
    len(
    [m for m in messages
     if m.get("status")=="DELIVERED"]
    ),


    "read":
    len(
    [m for m in messages
    if m.get("status")=="READ"]
    ),


    "failed":
    len(failed_queue),


    "campaigns":
    len(campaigns)


    }