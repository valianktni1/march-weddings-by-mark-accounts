import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCurrency, formatDateUK, getCurrentTaxYear } from "@/utils/formatters";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api/hmrc`;
const fieldClass = "w-full rounded-md border border-stone-300 bg-white p-2 text-sm";
const statusNames = { review: "Awaiting review", sending: "Sending / check outcome", accepted: "Accepted by sandbox", rejected: "Rejected by sandbox", unknown: "Outcome unknown — check before retrying" };

export function browserContext() {
  let device = localStorage.getItem("accounts_hmrc_device");
  if (!device) {
    device = crypto.randomUUID();
    localStorage.setItem("accounts_hmrc_device", device);
  }
  const offset = -new Date().getTimezoneOffset();
  const timezone = `UTC${offset >= 0 ? "+" : "-"}${String(Math.floor(Math.abs(offset) / 60)).padStart(2, "0")}:${String(Math.abs(offset) % 60).padStart(2, "0")}`;
  return {
    device_id: device, user_agent: navigator.userAgent, timezone,
    screen_width: window.screen.width, screen_height: window.screen.height,
    colour_depth: window.screen.colorDepth, scale: window.devicePixelRatio || 1,
    window_width: window.innerWidth, window_height: window.innerHeight,
  };
}

function errorMessage(error) {
  const detail = error.response?.data?.detail;
  return typeof detail === "string" ? detail : detail?.code || "The HMRC test could not be completed. Please check the connection and try again.";
}

export default function Hmrc() {
  const [query, setQuery] = useSearchParams();
  const [status, setStatus] = useState(null);
  const [history, setHistory] = useState([]);
  const [busy, setBusy] = useState("");
  const [year, setYear] = useState(getCurrentTaxYear());
  const [quarter, setQuarter] = useState("Q1");
  const [businessId, setBusinessId] = useState("");
  const [businesses, setBusinesses] = useState([]);
  const [obligations, setObligations] = useState([]);
  const [scenario, setScenario] = useState("DEFAULT");
  const [draft, setDraft] = useState(null);
  const [confirmation, setConfirmation] = useState("");
  const [preview, setPreview] = useState(null);
  const [headers, setHeaders] = useState(null);
  const [retrieved, setRetrieved] = useState(null);
  const ready = status?.enabled && status.setup_missing?.length === 0;
  const connected = ready && status?.connected;
  const years = Array.from({ length: Math.max(4, Number(getCurrentTaxYear().slice(0, 4)) - 2025 + 2) }, (_, i) => `${2025 + i}-${String(2026 + i).slice(-2)}`);

  async function refresh() {
    const [s, h] = await Promise.all([axios.get(`${API}/status`), axios.get(`${API}/history`)]);
    setStatus(s.data); setHistory(h.data);
  }
  useEffect(() => { refresh().catch((e) => toast.error(errorMessage(e))); }, []);
  useEffect(() => {
    const outcome = query.get("connection");
    if (outcome) {
      if (outcome === "success") toast.success("HMRC test user connected");
      else toast.error(outcome === "cancelled" ? "HMRC connection cancelled" : "HMRC test connection failed. Check the developer settings.");
      setQuery({}, { replace: true });
    }
  }, [query, setQuery]);
  useEffect(() => { setDraft(null); setConfirmation(""); setPreview(null); setRetrieved(null); setObligations([]); }, [year, quarter, businessId, scenario]);

  async function run(name, task) {
    setBusy(name);
    try { await task(); }
    catch (e) { toast.error(errorMessage(e)); }
    finally { setBusy(""); }
  }
  const inspectBody = () => ({ tax_year: year, scenario, context: browserContext() });
  const sampleBody = () => ({ ...inspectBody(), quarter, business_id: businessId, scenario });

  return <div className="space-y-6 pb-8">
    <div>
      <h1 className="text-3xl font-medium text-stone-900" style={{ fontFamily: "Playfair Display, serif" }}>HMRC test workspace</h1>
      <p className="mt-2 text-stone-600">Prepare for Making Tax Digital, one step at a time.</p>
    </div>
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950" role="status">
      <strong>Testing only. Live filing is unavailable.</strong> Test submissions use fictional sample figures and a generated HMRC test user. They do not fulfil a tax obligation. Your own accounts can be previewed below and cannot be sent from this page.
    </div>

    <Card><CardHeader><CardTitle>1. Set up the test connection</CardTitle></CardHeader><CardContent className="space-y-4">
      {!status ? <p>Loading connection…</p> : <>
        <p className="text-sm">{status.connected ? "A test user is connected." : "No test user connected yet."} {ready ? "Developer settings are ready." : "The server needs HMRC sandbox settings before you can connect."}</p>
        {!ready && <details className="rounded-md bg-stone-50 p-3 text-sm"><summary className="cursor-pointer font-medium">Setup checklist</summary>
          <ol className="my-3 list-decimal space-y-2 pl-5">
            <li>Create an application in the <a className="underline" href="https://developer.service.hmrc.gov.uk/" target="_blank" rel="noreferrer">HMRC Developer Hub</a> and subscribe to the sandbox APIs listed in the setup guide.</li>
            <li>Use <a className="underline" href="https://developer.service.hmrc.gov.uk/api-test-user" target="_blank" rel="noreferrer">HMRC’s test-user service</a> to generate an individual enrolled for MTD Income Tax. Use these test credentials when connecting.</li>
            <li>Configure the server using <code>docs/HMRC-SANDBOX.md</code>. Keep secrets out of this screen and out of GitHub.</li>
          </ol>
          <p className="font-medium">Redirect address to register:</p><p className="my-2 break-all font-mono text-xs">{status.redirect_uri}</p>
          <p>Sandbox switched on: {status.enabled ? "Yes" : "No"}</p>
          <ul className="mt-2 list-disc space-y-1 pl-5">{status.setup_missing.map((s) => <li key={s}>{s}</li>)}</ul>
        </details>}
        <div className="flex flex-wrap gap-2">
          <Button disabled={!ready || !!busy} onClick={() => run("connect", async () => { const r = await axios.post(`${API}/connect`); window.location.assign(r.data.url); })}>Connect HMRC test user</Button>
          <Button variant="outline" disabled={!status.connected || !!busy} onClick={() => run("disconnect", async () => { await axios.delete(`${API}/connection`); setDraft(null); setBusinesses([]); setBusinessId(""); setObligations([]); await refresh(); toast.success("Local HMRC test connection removed"); })}>Disconnect test user</Button>
          <Button variant="outline" disabled={!ready || !!busy} onClick={() => run("headers", async () => { const r = await axios.post(`${API}/sandbox/check-headers`, inspectBody()); setHeaders(r.data); })}>Check security headers</Button>
        </div>
        {headers && <div className="rounded-md border p-3 text-sm" aria-live="polite"><p className="font-medium">Header test: {headers.data?.code || "No result"}</p><p>{headers.data?.message}</p>
          {!!headers.missing_headers?.length && <p className="mt-2">Not collected: {headers.missing_headers.join(", ")}. These need a deployment review and, where applicable, agreement from HMRC.</p>}
          {!!headers.data?.errors?.length && <ul className="mt-2 list-disc pl-5">{headers.data.errors.map((e, i) => <li key={i}>{e.message}</li>)}</ul>}
          <p className="mt-2 text-stone-500">This test does not grant production access or establish HMRC recognition.</p>
        </div>}
      </>}
    </CardContent></Card>

    <Card><CardHeader><CardTitle>2. Review a fictional test update</CardTitle></CardHeader><CardContent className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-3">
        <label className="space-y-1 text-sm"><span>Tax year</span><select className={fieldClass} value={year} disabled={!!busy} onChange={(e) => setYear(e.target.value)}>{years.map((y) => <option key={y}>{y}</option>)}</select></label>
        <label className="space-y-1 text-sm"><span>Standard reporting quarter</span><select className={fieldClass} value={quarter} disabled={!!busy} onChange={(e) => setQuarter(e.target.value)}>{["Q1", "Q2", "Q3", "Q4"].map((q) => <option key={q}>{q}</option>)}</select></label>
        <label className="space-y-1 text-sm"><span>Test response</span><select className={fieldClass} value={scenario} disabled={!!busy} onChange={(e) => setScenario(e.target.value)}><option value="DEFAULT">Simulated response</option><option value="STATEFUL">Stateful test business</option></select></label>
      </div>
      <p className="text-sm text-stone-600">Figures run from 6 April up to the selected quarter end. This first version supports standard quarters for a sole trader. Annual returns and calendar-quarter businesses are outside this test workspace.</p>
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" disabled={!connected || !!busy} onClick={() => run("businesses", async () => { const r = await axios.post(`${API}/sandbox/businesses`, inspectBody()); const rows = (r.data.data?.listOfBusinesses || r.data.data?.businesses || []).filter((b) => b.typeOfBusiness === "self-employment"); setBusinesses(rows); if (rows.length) setBusinessId(rows[0].businessId); else toast.info("No self-employment test business returned"); })}>Load test businesses</Button>
        <Button variant="outline" disabled={!connected || !!busy} onClick={() => run("obligations", async () => { const r = await axios.post(`${API}/sandbox/obligations`, inspectBody()); setObligations(r.data.data?.obligations || []); })}>View simulated deadlines</Button>
      </div>
      <label className="block space-y-1 text-sm"><span>HMRC test business ID</span><input className={fieldClass} value={businessId} disabled={!!busy} onChange={(e) => setBusinessId(e.target.value.toUpperCase())} placeholder="Choose from the test businesses, or enter a created test business ID" list="hmrc-test-businesses" autoComplete="off"/><datalist id="hmrc-test-businesses">{businesses.map((b) => <option key={b.businessId} value={b.businessId}>{b.tradingName || b.businessId}</option>)}</datalist></label>
      {!!obligations.length && <div className="space-y-2 rounded-md bg-stone-50 p-3 text-sm"><p className="font-medium">Simulated HMRC deadlines</p>{obligations.filter((b) => b.typeOfBusiness === "self-employment").flatMap((b) => (b.obligationDetails || []).map((d, i) => <p key={`${b.businessId}-${i}`} className="break-words">{b.businessId}: {formatDateUK(d.periodStartDate)} – {formatDateUK(d.periodEndDate)} · due {formatDateUK(d.dueDate)} · {d.status}</p>))}</div>}
      <Button disabled={!connected || !!busy || !/^X[A-Z0-9]{14}$/.test(businessId)} onClick={() => run("review", async () => { const r = await axios.post(`${API}/sandbox/review`, sampleBody()); setDraft(r.data); setConfirmation(""); await refresh(); })}>Prepare sample review</Button>
      {draft && <div className="space-y-4 rounded-lg border border-stone-300 p-4">
        <p className="font-medium">Fictional sample · {draft.business_id} · {draft.scenario === "STATEFUL" ? "Stateful sandbox" : "Simulated sandbox response"}</p>
        <p className="text-sm">{formatDateUK(draft.payload.periodDates.periodStartDate)} to {formatDateUK(draft.payload.periodDates.periodEndDate)}</p>
        <dl className="grid grid-cols-2 gap-2 text-sm"><dt>Sample turnover</dt><dd className="text-right">{formatCurrency(draft.payload.periodIncome.turnover)}</dd><dt>Sample expenses</dt><dd className="text-right">{formatCurrency(draft.payload.periodExpenses.consolidatedExpenses)}</dd></dl>
        <p className="text-sm text-stone-600">These are fixed demonstration figures. They are unrelated to your accounts. A review expires after 15 minutes.</p>
        <label className="block space-y-1 text-sm"><span>Type SEND SAMPLE TO SANDBOX</span><input className={fieldClass} value={confirmation} disabled={!!busy || draft.status !== "review"} onChange={(e) => setConfirmation(e.target.value)} autoComplete="off"/></label>
        <Button className="h-auto min-h-10 max-w-full whitespace-normal text-center" disabled={!!busy || confirmation !== "SEND SAMPLE TO SANDBOX" || draft.status !== "review"} onClick={() => run("submit", async () => {
          // Disable this review immediately, including on an ambiguous network error.
          setDraft((d) => ({ ...d, status: "sending" }));
          try { const r = await axios.post(`${API}/sandbox/submit`, { review_id: draft.id, confirmation, context: browserContext() }); setDraft((d) => ({ ...d, status: r.data.status })); if (r.data.status === "accepted") toast.success("Sample accepted by the HMRC sandbox. No real tax filing was made."); else toast.error(statusNames[r.data.status] || "Check test history"); }
          finally { await refresh(); }
        })}>{busy === "submit" ? "Sending sample…" : "Send fictional sample to HMRC sandbox"}</Button>
        {draft.status !== "review" && <p className="text-sm" aria-live="polite">{statusNames[draft.status] || draft.status}. Check history before preparing another review.</p>}
      </div>}
      <Button variant="outline" disabled={!connected || !!busy || !/^X[A-Z0-9]{14}$/.test(businessId)} onClick={() => run("retrieve", async () => { const r = await axios.post(`${API}/sandbox/retrieve`, sampleBody()); setRetrieved(r.data.data); })}>Retrieve test summary</Button>
      {retrieved && <details className="rounded-md bg-stone-50 p-3 text-sm"><summary>Retrieved sandbox response {scenario === "DEFAULT" ? "(simulated; not proof that your sample was stored)" : "(stateful)"}</summary><pre className="mt-3 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify(retrieved, null, 2)}</pre></details>}
    </CardContent></Card>

    <Card><CardHeader><CardTitle>Your accounts: local cumulative preview</CardTitle></CardHeader><CardContent className="space-y-4">
      <p className="text-sm text-stone-600">Use the tax year and quarter above. This uses the same accounting ledger as your dashboard. Nothing from this preview is sent to HMRC.</p>
      <Button variant="outline" disabled={!!busy} onClick={() => run("preview", async () => { const r = await axios.get(`${API}/preview/${year}/${quarter}`); setPreview(r.data); })}>Preview my figures locally</Button>
      {preview && <div className="space-y-3 text-sm" aria-live="polite"><p>{formatDateUK(preview.start)} to {formatDateUK(preview.end)}</p><dl className="grid grid-cols-2 gap-2"><dt>Income</dt><dd className="text-right">{formatCurrency(preview.income)}</dd><dt>Expenses including mileage</dt><dd className="text-right">{formatCurrency(preview.expenses)}</dd><dt>Profit before tax adjustments</dt><dd className="text-right">{formatCurrency(preview.profit)}</dd></dl><p>{preview.notice}</p>
        {!!preview.close_blockers && <p className="text-amber-800">The full tax-year review has {preview.close_blockers} blocking checks to resolve.</p>}
        {preview.problems.map((p) => <p key={p} className="text-red-700">{p}. This preview is incomplete.</p>)}
      </div>}
    </CardContent></Card>

    <Card><CardHeader><CardTitle>Test submission history</CardTitle></CardHeader><CardContent className="space-y-3">
      <Button variant="outline" disabled={!!busy} onClick={() => run("refresh", refresh)}>Refresh history</Button>
      {!history.length && <p className="text-sm text-stone-500">No sample reviews or submissions yet.</p>}
      {history.map((r) => <div key={r.id} className="rounded-md border p-3 text-sm"><p className="font-medium">{statusNames[r.status] || r.status} · {r.tax_year} {r.quarter}</p><p className="mt-1 break-all text-stone-500">{new Date(r.created_at).toLocaleString("en-GB")} · {r.scenario === "STATEFUL" ? "Stateful test" : "Simulated response"} · {r.business_id}</p>
        {r.error && <p className="mt-1 text-red-700">{r.error.code}</p>}{r.correlation_id && <p className="mt-1 break-all text-xs">HMRC test correlation reference: {r.correlation_id}</p>}
        {!!r.missing_headers?.length && <p className="mt-1 text-amber-800">Security header collection still needs attention.</p>}
        {r.status === "accepted" && <p className="mt-1">Test environment only. Your real tax obligations are unchanged.</p>}
      </div>)}
    </CardContent></Card>
  </div>;
}
