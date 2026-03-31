import json
import os
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from datetime import datetime
import urllib.request

ddb = boto3.resource("dynamodb")
table = ddb.Table(os.environ["TABLE_NAME"])
AGENT_ENDPOINT = os.environ.get("AGENT_ENDPOINT", "")

TICKET_PROMPTS = {
    "VPC_CONNECTIVITY": "VPC {vpc_id} in region {region}의 네트워크 구성을 분석해주세요. 서브넷, 라우팅 테이블, IGW, NAT Gateway, NACL을 확인하고 인터넷 연결 가능 여부와 잠재적 문제점을 진단해주세요.",
    "TGW_ROUTE_CHECK": "Region {region}의 Transit Gateway 라우팅을 분석해주세요. 라우트 테이블, 블랙홀 라우트, 비대칭 경로 등 문제가 없는지 확인해주세요.",
    "VPN_STATUS": "Region {region}의 VPN 연결 상태를 확인해주세요. 터널 상태, BGP 세션, 연결 문제가 있는지 진단해주세요.",
    "SUBNET_CHECK": "VPC {vpc_id} in region {region}의 서브넷 구성을 분석해주세요. 각 서브넷의 가용 IP, 라우팅, public/private 구분, AZ 분산을 확인해주세요.",
    "SECURITY_GROUP_AUDIT": "VPC {vpc_id} in region {region}의 보안 그룹을 감사해주세요. 과도하게 열린 규칙, 0.0.0.0/0 인바운드 등 보안 위험을 식별해주세요.",
}

def build_prompt(ticket):
    template = TICKET_PROMPTS.get(ticket["type"], "")
    fields = ticket.get("fields", {})
    prompt = template.format(**fields) if template else f"Ticket: {ticket['type']}. Fields: {fields}. Analyze this network issue."
    prompt += f"\n\nTicket ID: {ticket['id']}, Title: {ticket.get('title', '')}"
    return prompt

def call_agent(prompt):
    if not AGENT_ENDPOINT:
        return {"error": "AGENT_ENDPOINT not configured"}
    try:
        payload = json.dumps({"prompt": prompt})
        session = boto3.Session()
        credentials = session.get_credentials().get_frozen_credentials()
        request = AWSRequest(method="POST", url=AGENT_ENDPOINT, data=payload, headers={"Content-Type": "application/json", "Accept": "application/json"})
        SigV4Auth(credentials, "bedrock-agentcore", "us-east-1").add_auth(request)
        req = urllib.request.Request(AGENT_ENDPOINT, data=payload.encode(), headers=dict(request.headers), method="POST")
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}

def respond(code, body):
    return {"statusCode": code, "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"}, "body": json.dumps(body, default=str)}

def lambda_handler(event, context):
    try:
        method = event["httpMethod"]
        path = event.get("path", "")
        path_params = event.get("pathParameters") or {}

        if method == "GET" and path == "/tickets":
            return respond(200, {"tickets": table.scan().get("Items", [])})
        if method == "POST" and path == "/tickets":
            body = json.loads(event["body"])
            tid = f"NET-{int(datetime.now().timestamp()*1000)}"
            item = {"id": tid, "type": body["type"], "title": body.get("title", ""), "fields": body.get("fields", {}), "status": "OPEN", "result": None, "created_at": datetime.now().isoformat()}
            table.put_item(Item=item)
            return respond(201, {"ticket": item})
        if method == "GET" and path_params.get("id"):
            r = table.get_item(Key={"id": path_params["id"]})
            return respond(200, r.get("Item", {})) if r.get("Item") else respond(404, {"error": "not found"})
        if method == "POST" and path.endswith("/process"):
            tid = path_params["id"]
            r = table.get_item(Key={"id": tid})
            if not r.get("Item"):
                return respond(404, {"error": "not found"})
            ticket = r["Item"]
            prompt = build_prompt(ticket)
            result = call_agent(prompt)
            ticket["status"] = "COMPLETED"
            ticket["result"] = {"prompt": prompt, "response": result}
            table.put_item(Item=ticket)
            return respond(200, ticket)
        return respond(404, {"error": "not found"})
    except Exception as e:
        return respond(500, {"error": str(e)})
