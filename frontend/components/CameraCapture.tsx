"use client";

import {useEffect, useRef, useState} from "react";
import {api, post, type Photo, type Plan, type Point, type Verification} from "@/lib/api";

const referenceHoles = ["A1", "J1", "J63", "A63"];

export default function CameraCapture({projectId, plan, images, onUploaded}: {projectId: string; plan: Plan; images: Photo[]; onUploaded: () => Promise<void>}) {
  const [photo, setPhoto] = useState<Photo | null>(images[0] ?? null);
  const [points, setPoints] = useState<Point[]>([]);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [run, setRun] = useState<Verification | null>(null);
  const alive = useRef(true);
  useEffect(() => {alive.current = true; return () => {alive.current = false;};}, []);

  async function upload(file: File) {
    setBusy(true); setError("");
    try {
      if (file.size > 10 * 1024 * 1024) throw new Error("Choose a PNG or JPEG smaller than 10 MB.");
      const ticket = await post<{upload_url: string}>("/images/uploads", {project_id: projectId, consent_for_training: consent});
      const uploaded = await api<Photo>(ticket.upload_url.replace("/api/v1", ""), {method: "PUT", body: file, headers: {"Content-Type": file.type}});
      if (!alive.current) return;
      setPhoto(uploaded); setPoints([]); setRun(null); await onUploaded();
    } catch (e) {if (alive.current) setError((e as Error).message);}
    finally {if (alive.current) setBusy(false);}
  }

  async function align() {
    if (!photo || points.length !== 4) return;
    setBusy(true); setError(""); setRun(null);
    try {
      const created = await post<{id: string}>("/verification-runs", {plan_id: plan.id, image_id: photo.id, calibration_points: points.map((p, index) => ({hole_id: referenceHoles[index], ...p}))});
      for (let attempt = 0; attempt < 60 && alive.current; attempt++) {
        const result = await api<Verification>(`/verification-runs/${created.id}`);
        if (!["pending", "running"].includes(result.status)) {
          setRun(result);
          if (result.status === "failed") throw new Error(result.results?.error ?? "Alignment failed. Check the reference holes.");
          return;
        }
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
      if (alive.current) throw new Error("Analysis is still queued. Keep the background worker running and retry later.");
    } catch (e) {if (alive.current) setError((e as Error).message);}
    finally {if (alive.current) setBusy(false);}
  }

  return <div className="camera-layout">
    <section className="panel photo-stage">
      <div className="section-heading"><div><span className="eyebrow">PHOTO ALIGNMENT</span><h2>Bring your board into view</h2></div><span className="pill">Manual calibration</span></div>
      {!photo ? <label className="upload-zone"><span className="upload-icon">↥</span><strong>Upload a top-down photo</strong><span>PNG or JPEG · up to 10 MB · no live camera required</span><input aria-label="Upload circuit photo" type="file" accept="image/png,image/jpeg" capture="environment" disabled={busy} onChange={e => e.target.files?.[0] && upload(e.target.files[0])}/></label> : <>
        <p className="muted">{points.length < 4 ? <>Click the exact center of hole <strong>{referenceHoles[points.length]}</strong> in the photo ({points.length + 1}/4).</> : "Four reference holes selected. Generate an overlay, then confirm the alignment yourself."}</p>
        <svg className="photo-canvas" viewBox={`0 0 ${photo.width} ${photo.height}`} style={{aspectRatio: `${photo.width}/${photo.height}`}}
          aria-label="Photo calibration area" role="img" onClick={event => {
            if (points.length >= 4 || busy) return;
            const transform = event.currentTarget.getScreenCTM();
            if (!transform) return;
            const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(transform.inverse());
            if (point.x < 0 || point.y < 0 || point.x >= photo.width || point.y >= photo.height) return;
            setPoints([...points, {x: point.x, y: point.y}]); setRun(null);
          }}>
          <image href={`/api/v1/images/${photo.id}/content`} width={photo.width} height={photo.height}/>
          {points.map((p, index) => <g key={index}><circle cx={p.x} cy={p.y} r={photo.width / 90} fill="#159b73" stroke="white" strokeWidth={photo.width / 400}/><text x={p.x + photo.width / 60} y={p.y} fill="white" stroke="#123e2b" paintOrder="stroke" strokeWidth={photo.width / 600} fontSize={photo.width / 35}>{referenceHoles[index]}</text></g>)}
          {run?.status === "needs_confirmation" && run.results?.overlay.jumpers.map(wire => <line key={wire.id} x1={wire.start.x} y1={wire.start.y} x2={wire.end.x} y2={wire.end.y} stroke={wire.color === "black" ? "#f3eecf" : wire.color} strokeWidth={photo.width / 160} opacity=".85"/>)}
          {run?.status === "needs_confirmation" && run.results?.overlay.components.map(component => {
            const pins = Object.values(component.pins), first = pins[0], last = pins.at(-1)!;
            return <g key={component.component_id}><line x1={first.x} y1={first.y} x2={last.x} y2={last.y} stroke="#69ebbe" strokeWidth={photo.width / 90}/><text x={first.x} y={first.y - photo.width / 50} fontSize={photo.width / 35} fill="white" stroke="#153d2d" strokeWidth={photo.width / 500} paintOrder="stroke">Expected {component.component_id}</text></g>;
          })}
        </svg>
        <div className="actions"><button className="primary" disabled={busy || points.length !== 4} onClick={align}>{busy ? "Processing…" : "Align expected layout"}</button><button disabled={busy} onClick={() => {setPoints([]); setRun(null);}}>Reset reference points</button><button disabled={busy} onClick={() => {setPhoto(null); setPoints([]); setRun(null);}}>Choose another photo</button></div>
      </>}
      {error && <div className="error" role="alert">{error}</div>}
    </section>
    <aside className="panel camera-guide"><span className="eyebrow">WHAT THIS CHECK DOES</span><h3>Alignment, with clear limits</h3><ol className="guide-list"><li>Keep the board near top-down and fully visible.</li><li>Use A1 → J1 → J63 → A63 on the terminal strips, excluding rails.</li><li>The overlay shows expected positions from your graph-checked plan.</li><li>Inspect alignment yourself; visible placement is not electrical continuity.</li></ol>
      <div className="notice">No trained detector is loaded. This view does not identify missing parts or verify wiring.</div>
      <label className="checkbox"><input type="checkbox" checked={consent} disabled={!!photo} onChange={e => setConsent(e.target.checked)}/>Allow this next upload to be used in future model training. Optional; off by default.</label>
      <p className="fine-print">Photo metadata is stripped. Photos expire after 30 days by default and can be deleted from your project.</p>
      {run?.results?.uncertainties && <div className="verification-result"><span className="pill warning">Needs your confirmation</span>{run.results.uncertainties.map(text => <p key={text}>{text}</p>)}</div>}
      {images.length > 0 && <><h4>Project photos</h4><div className="photo-list">{images.map(image => <button key={image.id} onClick={() => {setPhoto(image); setPoints([]); setRun(null);}} disabled={busy}>Photo {image.id.slice(0, 6)} · {image.width}×{image.height}</button>)}</div></>}
    </aside>
  </div>;
}
