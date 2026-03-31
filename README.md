# AWS Network MCP + AgentCore Demo

ITSM 티켓 시스템에서 네트워크 진단을 자동화하는 데모입니다. AWS Network MCP Server를 AgentCore Runtime에 배포하고, Strands Agent(LLM)가 자연어로 네트워크 문제를 분석합니다.

## 데모 영상

> 티켓 생성 → LLM이 자동으로 네트워크 분석 → 권장사항 포함 리포트 생성

## 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  [웹 UI - CloudFront]                                           │
│       ↓ HTTPS                                                   │
│  [API Gateway] → [Lambda - Ticket Handler]                      │
│                       ↓ SigV4                                   │
│  [AgentCore Runtime A - Strands Agent]                          │
│       ├── LLM (Bedrock Claude) — 자연어 분석, tool 선택         │
│       └── mcp-proxy-for-aws — IAM 인증으로 Runtime B 연결       │
│                       ↓ SigV4 HTTP                              │
│  [AgentCore Runtime B - Network MCP Server]                     │
│       └── 27개 네트워크 진단 도구                                │
│                       ↓ boto3                                   │
│  [AWS APIs - VPC, TGW, VPN, CloudWAN, Firewall, Flow Logs]     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 주요 기능

- **자연어 네트워크 분석**: "VPC의 서브넷 구성을 분석해주세요" → LLM이 적절한 tool 선택 → 분석 리포트 생성
- **멀티 tool 체이닝**: LLM이 여러 MCP tool을 순차적으로 호출하여 종합 분석
- **27개 네트워크 진단 도구**: VPC, Transit Gateway, Cloud WAN, VPN, Network Firewall, Flow Logs
- **마크다운 리포트**: 테이블, 권장사항, 보안 분석 포함
- **ITSM 연동 데모**: 정형 티켓 → 자연어 변환 → 자동 분석

## 프로젝트 구조

```
├── network-mcp-server/     # Runtime B - Network MCP Server
│   ├── server.py           # FastMCP 기반 네트워크 도구 서버
│   └── Dockerfile
├── strands-agent/          # Runtime A - Strands Agent + LLM
│   ├── server.py           # Agent + mcp-proxy-for-aws
│   └── Dockerfile
├── web-demo/               # 웹 UI + Lambda
│   ├── index.html          # 티켓 생성/조회 UI
│   ├── app.js              # 비동기 폴링 + 마크다운 렌더링
│   └── handler.py          # Lambda - 티켓 CRUD + Agent 호출
└── README.md
```

## 사전 요구사항

- AWS 계정 (Amazon Bedrock AgentCore 접근 가능)
- AWS CloudShell 접근 가능
- Bedrock Claude 모델 접근 권한 (us-east-1)
- IAM 권한: ECR, AgentCore, Bedrock, Lambda, API Gateway, S3, CloudFront, DynamoDB

## 배포 가이드

### Step 1: Network MCP Server 배포 (Runtime B)

#### 1-1. ECR 리포지토리 생성

AWS 콘솔 → Amazon ECR → **Create repository** → `network-mcp-agentcore`

#### 1-2. CloudShell에서 빌드 & 푸시

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=us-east-1
mkdir -p network-mcp-agentcore && cd network-mcp-agentcore

cat > server.py << 'EOF'
import logging, sys
from awslabs.aws_network_mcp_server.tools import cloud_wan, general, network_firewall, transit_gateway, vpc, vpn
from mcp.server.fastmcp import FastMCP
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
mcp = FastMCP(host="0.0.0.0", stateless_http=True)
for module in (general, cloud_wan, network_firewall, transit_gateway, vpc, vpn):
    for tool_name in module.__all__:
        func = getattr(module, tool_name)
        mcp.tool()(func)
def main():
    mcp.run(transport='streamable-http')
if __name__ == '__main__':
    main()
EOF

cat > Dockerfile << 'EOF'
FROM public.ecr.aws/docker/library/python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir awslabs.aws-network-mcp-server
COPY server.py .
EXPOSE 8000
ENV FASTMCP_HOST=0.0.0.0
ENV FASTMCP_PORT=8000
ENTRYPOINT ["python", "server.py"]
EOF

aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com
docker buildx create --use --name arm64builder 2>/dev/null || true
docker buildx build --platform linux/arm64 --load -t network-mcp-agentcore .
docker tag network-mcp-agentcore:latest $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/network-mcp-agentcore:latest
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/network-mcp-agentcore:latest
```

#### 1-3. AgentCore Runtime 배포

| 항목 | 값 |
|------|-----|
| Name | `networkMcpServer` |
| Source | ECR → `network-mcp-agentcore:latest` |
| Protocol | **MCP** |
| Inbound Auth | **IAM** |
| Security | **Public** |

#### 1-4. IAM Role 권한 추가

Service Role에 `ReadOnlyAccess` 정책 추가 (또는 최소 권한 정책)

#### 1-5. 동작 확인

Test endpoint에서:
```json
{"jsonrpc":"2.0","id":1,"method":"tools/list"}
```
→ 27개 도구 목록 반환 확인


### Step 2: Strands Agent 배포 (Runtime A)

#### 2-1. ECR 리포지토리 생성

AWS 콘솔 → Amazon ECR → **Create repository** → `strands-agent-multi-mcp`

#### 2-2. CloudShell에서 빌드 & 푸시

> ⚠️ `server.py`의 `url` 변수를 Step 1에서 생성한 Runtime B의 엔드포인트로 변경하세요.

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=us-east-1
mkdir -p strands-agent-multi-mcp && cd strands-agent-multi-mcp

# server.py와 Dockerfile은 strands-agent/ 폴더 참조
# url 변수를 본인의 Runtime B 엔드포인트로 수정 필요

aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com
docker buildx create --use --name arm64builder 2>/dev/null || true
docker buildx build --platform linux/arm64 --load -t strands-agent-multi-mcp .
docker tag strands-agent-multi-mcp:latest $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/strands-agent-multi-mcp:latest
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/strands-agent-multi-mcp:latest
```

#### 2-3. AgentCore Runtime 배포

| 항목 | 값 |
|------|-----|
| Name | `strandsAgentMultiMcp` |
| Source | ECR → `strands-agent-multi-mcp:latest` |
| Protocol | **HTTP** |
| Inbound Auth | **IAM** |
| Security | **Public** |

#### 2-4. IAM Role 권한 추가

Service Role에 인라인 정책 추가:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
            "Resource": "arn:aws:bedrock:*::foundation-model/*"
        },
        {
            "Effect": "Allow",
            "Action": "bedrock-agentcore:InvokeAgentRuntime",
            "Resource": "arn:aws:bedrock-agentcore:us-east-1:*:runtime/*"
        }
    ]
}
```

#### 2-5. 동작 확인

Test endpoint에서:
```json
{"prompt": "us-east-1 리전에 있는 VPC 목록을 조회해주세요."}
```
→ LLM이 `list_vpcs` tool 호출 → 실제 VPC 데이터 + 분석 결과 반환


### Step 3: 웹 데모 UI 배포

CDK 또는 수동으로 아래 리소스를 생성합니다:

| 리소스 | 용도 |
|--------|------|
| S3 + CloudFront | 정적 웹 호스팅 (index.html, app.js) |
| API Gateway (REST) | 티켓 API |
| Lambda (Python 3.12) | 티켓 CRUD + Runtime A 호출 |
| DynamoDB | 티켓 저장 |

#### Lambda 환경변수

| 변수 | 값 |
|------|-----|
| `TABLE_NAME` | DynamoDB 테이블 이름 |
| `AGENT_ENDPOINT` | Runtime A 엔드포인트 URL |

```
https://bedrock-agentcore.<REGION>.amazonaws.com/runtimes/<RUNTIME_ID>/invocations?qualifier=DEFAULT&accountId=<ACCOUNT_ID>
```

#### Lambda IAM 권한 추가

- `dynamodb:*` (CDK 자동)
- `bedrock-agentcore:InvokeAgentRuntime` (수동 추가)

#### Lambda Timeout

120초 이상 (LLM reasoning 시간 고려)

---

## 제공되는 네트워크 도구 (27개)

| 카테고리 | 주요 도구 | 설명 |
|----------|-----------|------|
| General | `get_path_trace_methodology`, `find_ip_address`, `get_eni_details` | IP/ENI 조회, 경로 추적 |
| VPC | `list_vpcs`, `get_vpc_network`, `get_vpc_flow_logs` | VPC 통합 조회 |
| Transit Gateway | `list_transit_gateways`, `get_tgw`, `get_all_tgw_routes`, `detect_tgw_inspection` | TGW 라우팅, 방화벽 탐지 |
| Cloud WAN | `list_core_networks`, `get_cwan`, `get_cwan_routes`, `simulate_cwan_route_change` | Cloud WAN 토폴로지 |
| VPN | `list_vpn_connections` | Site-to-Site VPN 상태 |
| Network Firewall | `list_firewalls`, `get_firewall_rules`, `get_firewall_flow_logs` | 방화벽 정책/로그 |

## 핵심 기술

- **[mcp-proxy-for-aws](https://pypi.org/project/mcp-proxy-for-aws/)**: IAM SigV4로 AgentCore Runtime MCP 서버에 인증 — OAuth 설정 불필요
- **[Strands Agents SDK](https://strandsagents.com/)**: 모델 기반 AI Agent 프레임워크
- **[awslabs.aws-network-mcp-server](https://awslabs.github.io/mcp/servers/aws-network-mcp-server)**: AWS 네트워크 진단 MCP 서버

## 참고 자료

- [AgentCore Runtime 공식 문서](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agents-tools-runtime.html)
- [MCP Server → AgentCore 배포 튜토리얼](https://dev.to/aws/from-local-mcp-server-to-aws-deployment-in-two-commands-code-only-5c4d)
- [mcp-proxy-for-aws 소개](https://dev.to/aws/no-oauth-required-an-mcp-client-for-aws-iam-k1o)
- [AWS Network MCP Server](https://awslabs.github.io/mcp/servers/aws-network-mcp-server)

## License

This project is for demonstration purposes.
