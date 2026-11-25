// Supabase Edge Function source. Deploy to NEW project only. Set verify_jwt=false for Meta callback.
const enc = new TextEncoder();
const hex = (x: ArrayBuffer) => [...new Uint8Array(x)].map(v=>v.toString(16).padStart(2,"0")).join("");
function same(a:string,b:string):boolean {
  if(a.length!==b.length)return false;
  let diff=0;for(let i=0;i<a.length;i++)diff|=a.charCodeAt(i)^b.charCodeAt(i);return diff===0;
}
async function signed(raw:Uint8Array,secret:string,header:string|null):Promise<boolean>{
  if(!header||!/^sha256=[a-f0-9]{64}$/.test(header))return false;
  const k=await crypto.subtle.importKey("raw",enc.encode(secret),{name:"HMAC",hash:"SHA-256"},false,["sign"]);
  return same(header,"sha256="+hex(await crypto.subtle.sign("HMAC",k,raw)));
}
async function rpc(name:string,body:unknown){
  const base=Deno.env.get("SUPABASE_URL")!;
  const key=Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  const expected=Deno.env.get("RB_NATIVE_PROJECT_REF")!;
  if(!expected||new URL(base).hostname!==expected+".supabase.co")throw new Error("project_mismatch");
  // Explicitly prohibit the two existing project refs.
  if(["xlkdzrhzizuftbnitodr","tdiamhxzzqjwaygjmnrp"].includes(expected))throw new Error("production_blocked");
  const r=await fetch(base+"/rest/v1/rpc/"+name,{method:"POST",headers:{apikey:key,Authorization:"Bearer "+key,"Content-Type":"application/json"},body:JSON.stringify(body),signal:AbortSignal.timeout(10000)});
  if(!r.ok)throw new Error("rpc_failed_"+r.status);
  return await r.json();
}
Deno.serve(async(req)=>{
  const url=new URL(req.url);
  const verify=Deno.env.get("META_WEBHOOK_VERIFY_TOKEN");
  if(req.method==="GET"){
    const challenge=url.searchParams.get("hub.challenge");
    return verify&&challenge&&url.searchParams.get("hub.mode")==="subscribe"&&same(url.searchParams.get("hub.verify_token")||"",verify)
      ? new Response(challenge,{status:200}):new Response("Forbidden",{status:403});
  }
  if(req.method!=="POST")return new Response("Method not allowed",{status:405});
  const secret=Deno.env.get("META_APP_SECRET"),recipient=Deno.env.get("META_IG_ACCOUNT_ID");
  if(!secret||!recipient)return new Response("Not configured",{status:503});
  if(Number(req.headers.get("content-length")||0)>1024*1024)return new Response("Too large",{status:413});
  const raw=new Uint8Array(await req.arrayBuffer());
  if(raw.length>1024*1024)return new Response("Too large",{status:413});
  if(!await signed(raw,secret,req.headers.get("x-hub-signature-256")))return new Response("Forbidden",{status:403});
  let body;try{body=JSON.parse(new TextDecoder().decode(raw));}catch{return new Response("Invalid JSON",{status:400});}
  if(body.object!=="instagram"||!Array.isArray(body.entry))return new Response("Ignored",{status:200});
  try{
    for(const entry of body.entry){
      if(String(entry.id)!==recipient||!Array.isArray(entry.messaging))continue;
      for(const event of entry.messaging){
        const m=event.message,s=event.sender?.id,r=event.recipient?.id;
        if(r!==recipient||typeof s!=="string"||!m||typeof m.mid!=="string"||m.is_echo||m.is_deleted)continue;
        const challenge=typeof m.text==="string"?m.text.trim().match(/^RB-VERIFY [A-Za-z0-9_-]{24,100}$/):null;
        if(challenge){
          await rpc("rb_native_verify_sender",{p_recipient:r,p_sender:s,p_hash:hex(await crypto.subtle.digest("SHA-256",enc.encode(challenge[0])))});
          continue;
        }
        // The RPC atomically checks sender approval; unapproved DM contents are not persisted.
        await rpc("rb_native_enqueue",{p_recipient:r,p_sender:s,p_mid:m.mid,p_payload:{text:typeof m.text==="string"?m.text:"",attachments:Array.isArray(m.attachments)?m.attachments:[],timestamp:event.timestamp??null}});
      }
    }
    return new Response("OK",{status:200});
  }catch{return new Response("Retry",{status:503});}
});
