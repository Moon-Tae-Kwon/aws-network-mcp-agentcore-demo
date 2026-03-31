import json, os, boto3, urllib.request
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from datetime import datetime

ddb = boto3.resource("dynamodb")
table = ddb.Table(os.environ["TABLE_NAME"])
AGENT_ENDPOINT = os.environ.get("AGENT_ENDPOINT", "")

IMPACT_SUFFIX = """

마지막으로 반드시 다음 영향도 분석을 포함해주세요:
- 이 요청을 처리할 경우 기존 트래픽에 미치는 영향
- 변경 시 주의사항 및 위험 요소
- 롤백 방안"""

TICKET_PROMPTS = {
    "CONNECTIVITY_REQUEST": """신규 네트워크 통신 요청입니다.
소스: {src_ip} (region: {region})
목적지: {dst_ip}
포트: {port}
프로토콜: {protocol}

다음을 분석해주세요:
1. 소스 IP와 목적지 IP가 각각 어떤 VPC/서브넷에 있는지 찾아주세요 (find_ip_address 사용)
2. 두 IP 간 네트워크 경로를 추적해주세요 (라우트 테이블, TGW, 피어링 등)
3. 현재 이 통신이 가능한 상태인지 판단해주세요
4. 불가능하다면 어떤 리소스(라우트 테이블, 보안 그룹, NACL 등)를 수정해야 하는지 구체적으로 알려주세요""" + IMPACT_SUFFIX,

    "FIREWALL_CHECK": """방화벽 정책 확인 요청입니다.
소스: {src_ip}
목적지: {dst_ip}
포트: {port}
리전: {region}

다음을 분석해주세요:
1. 소스와 목적지 IP의 위치를 찾아주세요
2. 경로에 Network Firewall이 있는지 확인해주세요
3. 방화벽 규칙에서 이 트래픽이 허용되는지 확인해주세요
4. 차단된다면 어떤 규칙을 추가/수정해야 하는지 알려주세요""" + IMPACT_SUFFIX,

    "INTERNET_ACCESS": """인터넷 접근 요청입니다.
대상 IP: {src_ip}
리전: {region}

다음을 분석해주세요:
1. 해당 IP가 위치한 VPC/서브넷을 찾아주세요
2. 인터넷 접근 경로를 확인해주세요 (IGW, NAT Gateway, 라우팅)
3. 보안 그룹과 NACL에서 아웃바운드 트래픽이 허용되는지 확인해주세요
4. 인터넷 접근이 불가능하다면 필요한 작업을 알려주세요""" + IMPACT_SUFFIX,
}

def build_prompt(ticket):
    template = TICKET_PROMPTS.get(ticket["type"], "")
    fields = ticket.get("fields", {})
    try:
        prompt = template.format(**fields)
    except KeyError:
        prompt = f"Ticket: {ticket['type']}. Fields: {fields}. Analyze this network request."
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
