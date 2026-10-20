"use client";

import {useEffect, useState} from "react";
import {api, post, type Photo, type Point} from "@/lib/api";

type Box = Point & {width: number; height: number; class_name: string};
type Pilot = {id: string; condition: string; duration_seconds: number | null; error_count: number; help_count: number};

export default function ResearchPanel({projectId, images}: {projectId: string; images: Photo[]}) {
  const [photoId, setPhotoId] = useState(images[0]?.id ?? "");
  const photo = images.find(image => image.id === photoId);
  const [boxes, setBoxes] = useState<Box[]>([]), [start, setStart] = useState<Point | null>(null);
  const [className, setClassName] = useState("resistor"), [setup, setSetup] = useState(""), [session, setSession] = useState("");
  const [reviewed, setReviewed] = useState(false), [message, setMessage] = useState(""), [error, setError] = useState("");
  const [condition, setCondition] = useState("guided"), [pilots, setPilots] = useState<Pilot[]>([]), [activePilot, setActivePilot] = useState("");
  const [errors, setErrors] = useState(0), [help, setHelp] = useState(0), [busy, setBusy] = useState(false);
  useEffect(() => {api<Pilot[]>("/pilot-sessions").then(setPilots).catch(() => {});}, []);

  async function action(work: () => Promise<void>) {
    setBusy(true); setError(""); setMessage("");
    try {await work();} catch (e) {setError((e as Error).message);} finally {setBusy(false);}
  }

  async function download(path: string, filename: string) {
    const data = await api<unknown>(path), url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type: "application/json"}));
    const link = document.createElement("a"); link.href = url; link.download = filename; link.click(); URL.revokeObjectURL(url);
  }

  return <div className="research-grid">
    <section className="panel"><div className="section-heading"><div><span className="eyebrow">DATASET WORKBENCH</span><h2>Label real examples</h2></div><span className="pill">Training preparation</span></div><p className="muted">Draw boxes on your own photos. Only reviewed photos with explicit training consent enter the dataset export.</p>
      {photo ? <><label>Photo<select value={photoId} onChange={e => {setPhotoId(e.target.value); setBoxes([]);}}>{images.map(image => <option key={image.id} value={image.id}>{image.id.slice(0, 8)} · training {image.consent_for_training ? "allowed" : "not allowed"}</option>)}</select></label>
        <div className="form-row"><label>Class<select value={className} onChange={e => setClassName(e.target.value)}>{["resistor", "led", "push_button", "wire_endpoint", "board_outline"].map(value => <option key={value}>{value}</option>)}</select></label><button onClick={() => setBoxes(boxes.slice(0, -1))} disabled={!boxes.length}>Undo box</button></div>
        <svg className="photo-canvas annotation-canvas" viewBox={`0 0 ${photo.width} ${photo.height}`} style={{aspectRatio: `${photo.width}/${photo.height}`}} aria-label="Draw annotation boxes" role="img"
          onPointerDown={event => {const r = event.currentTarget.getBoundingClientRect(); event.currentTarget.setPointerCapture(event.pointerId); setStart({x: (event.clientX-r.left)/r.width*photo.width, y: (event.clientY-r.top)/r.height*photo.height});}}
          onPointerUp={event => {if (!start) return; const r = event.currentTarget.getBoundingClientRect(); const end = {x: Math.max(0, Math.min(photo.width, (event.clientX-r.left)/r.width*photo.width)), y: Math.max(0, Math.min(photo.height, (event.clientY-r.top)/r.height*photo.height))}; const box = {class_name: className, x: Math.min(start.x, end.x), y: Math.min(start.y, end.y), width: Math.abs(start.x-end.x), height: Math.abs(start.y-end.y)}; if (box.width > 2 && box.height > 2) setBoxes([...boxes, box]); setStart(null);}}>
          <image href={`/api/v1/images/${photo.id}/content`} width={photo.width} height={photo.height}/>
          {boxes.map((box, index) => <g key={index}><rect x={box.x} y={box.y} width={box.width} height={box.height} fill="#159b7333" stroke="#68edb4" strokeWidth={photo.width/300}/><text x={box.x} y={box.y+photo.width/30} fill="white" stroke="#123e2b" strokeWidth={photo.width/600} paintOrder="stroke" fontSize={photo.width/40}>{box.class_name}</text></g>)}
        </svg>
        <div className="form-row"><label>Physical setup ID<input value={setup} onChange={e => setSetup(e.target.value)} placeholder="e.g. lab1-led-setup01"/></label><label>Capture session ID<input value={session} onChange={e => setSession(e.target.value)} placeholder="e.g. session-2026-10-20"/></label></div>
        <label className="checkbox"><input type="checkbox" checked={reviewed} onChange={e => setReviewed(e.target.checked)}/>I reviewed these labels, including any intentionally empty image.</label>
        <button className="primary" disabled={busy || !setup || !session} onClick={() => action(async () => {await post(`/images/${photo.id}/annotations`, {setup_id: setup, capture_session_id: session, boxes, review_status: reviewed ? "reviewed" : "draft"}); setMessage("Annotation version saved. Training consent remains unchanged.");})}>Save annotation version ({boxes.length} boxes)</button>
      </> : <div className="empty-state"><h3>No photos yet</h3><p>Upload a photo in the Photo alignment tab first.</p></div>}
      <div className="actions"><button disabled={busy} onClick={() => action(() => download("/datasets/export", "circuitpilot-dataset-manifest.json"))}>Export consented dataset manifest</button></div>
      <p className="fine-print">The export contains authenticated photo-download URLs, not public images. Group splits by setup and capture session before training. No trained model or accuracy is claimed.</p>
    </section>
    <aside className="panel"><span className="eyebrow">USER PILOT</span><h2>Measure the difference</h2><p className="muted">Record observed assembly time, errors, and help requests. These are measurements you enter, not automatically detected outcomes.</p>
      <label>Study condition<select value={condition} disabled={!!activePilot} onChange={e => setCondition(e.target.value)}><option value="guided">CircuitPilot guidance</option><option value="control">Control / standard diagram</option></select></label>
      {!activePilot ? <button className="primary" disabled={busy} onClick={() => action(async () => {const result = await post<{id: string}>("/pilot-sessions", {project_id: projectId, condition}); setActivePilot(result.id); setErrors(0); setHelp(0);})}>Start timed session</button> : <><div className="notice success">Session is running. Record what you observe.</div><div className="form-row"><label>Assembly errors<input type="number" min="0" max="1000" value={errors} onChange={e => setErrors(Number(e.target.value))}/></label><label>Help requests<input type="number" min="0" max="1000" value={help} onChange={e => setHelp(Number(e.target.value))}/></label></div><button className="primary" disabled={busy} onClick={() => action(async () => {await post(`/pilot-sessions/${activePilot}/complete`, {error_count: errors, help_count: help}); setActivePilot(""); setPilots(await api<Pilot[]>("/pilot-sessions")); setMessage("Pilot measurement saved.");})}>Finish and save measurement</button></>}
      <div className="pilot-results"><h4>Your completed measurements</h4>{pilots.filter(p => p.duration_seconds !== null).length ? pilots.filter(p => p.duration_seconds !== null).map(p => <div className="pilot-row" key={p.id}><strong>{p.condition}</strong><span>{Math.round(p.duration_seconds!)} s · {p.error_count} errors · {p.help_count} help</span></div>) : <p className="muted">No completed sessions. No user-value results are available yet.</p>}</div>
      <button disabled={busy} onClick={() => action(() => download("/pilot-sessions", "circuitpilot-pilot-results.json"))}>Export pilot measurements</button>
      <details className="privacy"><summary>Privacy and deletion</summary><p>Accounts and project metadata are stored in the configured database. Photos are stored privately, stripped of metadata, and expire after 30 days by default. Training consent defaults to off. Export or delete projects from the workspace menu; deleting a project removes its photos, annotations, plans, and measurements. This is a development privacy notice; institutional pilot terms require review.</p></details>
    </aside>
    {error && <div className="error" role="alert">{error}</div>}{message && <div className="notice success" role="status">{message}</div>}
  </div>;
}
