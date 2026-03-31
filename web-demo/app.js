const API = "https://p8krel4vi6.execute-api.us-east-1.amazonaws.com/prod";
const FD = {
  CONNECTIVITY_REQUEST: [{id:"src_ip",l:"Source IP",v:""},{id:"dst_ip",l:"Destination IP",v:""},{id:"port",l:"Port",v:"443"},{id:"protocol",l:"Protocol",v:"TCP"},{id:"region",l:"Region",v:"us-east-1"}],
  FIREWALL_CHECK: [{id:"src_ip",l:"Source IP",v:""},{id:"dst_ip",l:"Destination IP",v:""},{id:"port",l:"Port",v:"443"},{id:"region",l:"Region",v:"us-east-1"}],
  INTERNET_ACCESS: [{id:"src_ip",l:"Target IP",v:""},{id:"region",l:"Region",v:"us-east-1"}]
};
let sel=null;
function uf(){const t=document.getElementById("tType").value,c=document.getElementById("df");if(!t||!FD[t]){c.innerHTML="";return}c.innerHTML=FD[t].map(f=>`<label>${f.l}</label><input id="f_${f.id}" placeholder="${f.v}" value="${f.v}">`).join("")}
async function ct(){const t=document.getElementById("tType").value;if(!t)return alert("Select a ticket type");const fields={};(FD[t]||[]).forEach(f=>{fields[f.id]=document.getElementById(`f_${f.id}`).value});const r=await fetch(API+"/tickets",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({type:t,title:document.getElementById("tTitle").value||t+" request",fields})});const d=await r.json();rt();st(d.ticket.id)}
async function rt(){const r=await fetch(API+"/tickets"),d=await r.json(),l=document.getElementById("tl");if(!d.tickets.length){l.innerHTML='<div class="empty" style="height:100px"><span style="font-size:13px">No tickets yet</span></div>';return}l.innerHTML=d.tickets.sort((a,b)=>b.created_at.localeCompare(a.created_at)).map(t=>`<div class="tc ${sel===t.id?'act':''}" onclick="st('${t.id}')"><div class="th"><span class="tid">${t.id}</span><span class="st st-${t.status}">${t.status}</span></div><div class="tt">${t.type} — ${t.title}</div></div>`).join("")}
async function st(id){sel=id;rt();const r=await fetch(API+"/tickets/"+id),t=await r.json();rr(t)}
function parseMcp(res){try{const r=res.response||res;let result=r.result||r;if(typeof result==='string'){try{result=JSON.parse(result)}catch(e){return{_md:result}}}if(result.content){const text=result.content.find(c=>c.text)?.text;if(text)return{_md:text}}if(result.structuredContent?.result)return result.structuredContent.result;return res}catch(e){return res}}

function renderResult(data){
  if(data._md){return `<div class="md-body">${marked.parse(data._md)}</div>`}
  if(data.vpc)return renderResourceMap(data);
  return renderRaw(data);
}
function badge(text,color){return `<span style="background:${color}15;color:${color};padding:2px 8px;border-radius:6px;font-size:11px;font-weight:600">${text}</span>`}
function sid(id){return id?id.split('-').pop().slice(0,7):''}
function renderRaw(data){return `<div class="rj"><pre>${JSON.stringify(data,null,2)}</pre></div>`}

function renderResourceMap(data){
  const v=data.vpc;if(!v)return'';
  const conns=[];
  if(data.internet_gateway)conns.push({type:'IGW',id:data.internet_gateway.id,icon:'🌍',color:'#00b894'});
  (data.nat_gateways||[]).forEach(n=>conns.push({type:'NAT GW',id:n.id||n.NatGatewayId||'',icon:'🔄',color:'#fdcb6e'}));
  (data.vpc_endpoints||[]).forEach(e=>conns.push({type:'Endpoint',id:e.id||e.VpcEndpointId||'',icon:'🔗',color:'#74b9ff'}));
  const tgws=new Set();
  (data.route_tables||[]).forEach(rt=>rt.routes.forEach(r=>{if(r.target&&r.target.startsWith('tgw-'))tgws.add(r.target)}));
  tgws.forEach(t=>conns.push({type:'TGW',id:t,icon:'🔀',color:'#a29bfe'}));
  const azMap={};
  (data.subnets||[]).forEach(s=>{if(!azMap[s.az])azMap[s.az]=[];azMap[s.az].push(s)});
  let h=`<div class="rmap"><div class="rmap-vpc"><div class="rmap-vpc-label">🌐 VPC: ${v.id}</div><div class="rmap-vpc-cidr">${v.cidr} · ${v.region}</div></div><div class="rmap-azs">`;
  Object.keys(azMap).sort().forEach(az=>{
    h+=`<div class="rmap-az"><div class="rmap-az-label">${az}</div>`;
    azMap[az].forEach(s=>{
      const tc=s.type==='public'?'#00b894':'#6c5ce7';
      const rt=data.route_tables?.find(r=>r.id===s.route_table_id);
      h+=`<div class="rmap-subnet" style="border-left:3px solid ${tc}"><div class="rmap-sub-head"><span class="mono">${sid(s.id)}</span>${badge(s.type,tc)}</div><div class="rmap-sub-cidr">${s.cidr}</div>`;
      if(rt){h+=`<div class="rmap-rt">→ ${sid(rt.id)} ${badge(rt.type,rt.type==='main'?'#fdcb6e':'#74b9ff')}<div class="rmap-routes">`;
        rt.routes.forEach(r=>{const hi=conns.some(c=>r.target.includes(sid(c.id)));h+=`<div class="rmap-route"><span class="mono">${r.destination}</span><span class="rmap-arrow">→</span><span class="mono${hi?' rmap-hl':''}">${r.target}</span></div>`});
        h+=`</div></div>`}
      h+=`</div>`});
    h+=`</div>`});
  h+=`</div>`;
  if(conns.length){h+=`<div class="rmap-conns"><div class="rmap-conns-label">Network Connections (${conns.length})</div><div class="rmap-cg">`;
    conns.forEach(c=>{h+=`<div class="rmap-conn" style="border-color:${c.color}"><span>${c.icon}</span><div class="rmap-ct">${c.type}</div><div class="mono rmap-ci">${sid(c.id)}</div></div>`});
    h+=`</div></div>`}
  if(data.network_acls?.length){h+=`<div class="rmap-conns"><div class="rmap-conns-label">NACLs</div>`;
    data.network_acls.forEach(acl=>{const al=acl.rules.filter(r=>r.action==='allow').length,dn=acl.rules.filter(r=>r.action==='deny').length;
      h+=`<div style="padding:6px 0"><span class="mono">${sid(acl.id)}</span> ${badge(al+' allow','#00b894')} ${badge(dn+' deny','#ff6b6b')}</div>`});
    h+=`</div>`}
  h+=`</div>`;return h}

function renderVpc(data){return data.vpc?renderResourceMap(data):renderRaw(data)}

function rr(t){
  const a=document.getElementById("ra"),fh=Object.entries(t.fields||{}).map(([k,v])=>`<div class="mi"><div class="ml">${k}</div><div class="mv">${v}</div></div>`).join("");
  let rh="";
  if(t.result){const res=t.result,mcpData=parseMcp(res),isError=res.response?.result?.isError||mcpData?.error;
    rh=`<div class="rs"><h3>⚡ Agent Analysis</h3><div class="rm"><div class="mi"><div class="ml">Status</div><div class="mv" style="color:${isError?'var(--rd)':'var(--gr)'}">${isError?'error':'success'}</div></div><div class="mi"><div class="ml">Mode</div><div class="mv" style="color:var(--ac2)">LLM + Network MCP</div></div></div></div>`;
    if(res.prompt){rh+=`<div class="rs"><h3>📝 Prompt Sent</h3><div class="rj"><pre>${res.prompt}</pre></div></div>`}
    rh+=isError?`<div class="rs"><h3>❌ Error</h3>${renderRaw(mcpData)}</div>`:`<div class="rs"><h3>📊 Network Analysis</h3><div class="results-grid">${renderResult(mcpData)}</div></div>`
  }else{rh=`<button class="btn btn-g" onclick="pt('${t.id}')">▶ Process Ticket (Call Network MCP)</button>`}
  a.innerHTML=`<div class="rs"><h3>Ticket Info</h3><div class="rm"><div class="mi"><div class="ml">Ticket ID</div><div class="mv">${t.id}</div></div><div class="mi"><div class="ml">Type</div><div class="mv">${t.type}</div></div><div class="mi"><div class="ml">Status</div><div class="mv"><span class="st st-${t.status}">${t.status}</span></div></div><div class="mi"><div class="ml">Created</div><div class="mv">${new Date(t.created_at).toLocaleString()}</div></div></div></div><div class="rs"><h3>Input Fields → MCP Parameters</h3><div class="rm">${fh}</div></div>${rh}`}
async function pt(id){const btn=event.target;btn.disabled=true;btn.textContent="⏳ Analyzing...";fetch(API+"/tickets/"+id+"/process",{method:"POST",headers:{"Content-Type":"application/json"}}).catch(()=>{});setTimeout(()=>pollTicket(id),3000)}
async function pollTicket(id){const r=await fetch(API+"/tickets/"+id);const t=await r.json();if(t.status==="COMPLETED"){rt();rr(t)}else{setTimeout(()=>pollTicket(id),3000)}}
