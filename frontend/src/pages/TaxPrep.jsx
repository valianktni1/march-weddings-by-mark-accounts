import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  AlertCircle, Archive, CheckCircle2, Download, FileCheck2, LockKeyhole,
  PoundSterling, RefreshCw, RotateCcw, ShieldCheck, TrendingDown,
  TrendingUp, TriangleAlert,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { getCurrentTaxYear } from "@/utils/formatters";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const money = (value) => new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(Number(value || 0));
const dateTime = (value) => {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("en-GB");
};
const errorText = (error, fallback) => {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail?.message) return detail.message;
  return fallback;
};

export default function TaxPrep() {
  const [taxYears, setTaxYears] = useState([]);
  const [taxYear, setTaxYear] = useState(getCurrentTaxYear());
  const [data, setData] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [closeOpen, setCloseOpen] = useState(false);
  const [reopenOpen, setReopenOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const [reviewResponse, historyResponse] = await Promise.all([
        axios.get(`${API}/tax-year-close/${taxYear}`),
        axios.get(`${API}/tax-year-close/${taxYear}/history`),
      ]);
      setData(reviewResponse.data);
      setHistory(historyResponse.data || []);
    } catch (error) {
      toast.error(errorText(error, "Could not load the tax-year review"));
    } finally {
      setLoading(false);
    }
  }, [taxYear]);

  useEffect(() => {
    axios.get(`${API}/tax-years`).then((response) => {
      setTaxYears(response.data || []);
      if (!(response.data || []).some((item) => item.id === taxYear) && response.data?.length) setTaxYear(response.data[0].id);
    });
  }, [taxYear]);
  useEffect(() => { load(); }, [load]);

  const resetDialog = () => { setReason(""); setConfirmation(""); setAcknowledged(false); };
  const closeYear = async () => {
    setWorking(true);
    try {
      await axios.post(`${API}/tax-year-close/${taxYear}/close`, { confirmation, reason, acknowledge_warnings: acknowledged });
      toast.success(`${taxYear} is closed and its evidence pack is ready`);
      setCloseOpen(false); resetDialog(); await load(true);
    } catch (error) { toast.error(errorText(error, "Tax year could not be closed")); }
    finally { setWorking(false); }
  };
  const reopenYear = async () => {
    setWorking(true);
    try {
      await axios.post(`${API}/tax-year-close/${taxYear}/reopen`, { confirmation, reason });
      toast.success(`${taxYear} has been reopened; the previous evidence pack was retained`);
      setReopenOpen(false); resetDialog(); await load(true);
    } catch (error) { toast.error(errorText(error, "Tax year could not be reopened")); }
    finally { setWorking(false); }
  };
  const downloadPack = async () => {
    try {
      const response = await axios.get(`${API}/tax-year-close/${taxYear}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(response.data);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = data?.close?.pack?.pack_filename || `weddings_by_mark_tax_year_${taxYear}.zip`;
      anchor.click(); URL.revokeObjectURL(url); toast.success("Evidence pack downloaded");
    } catch (error) { toast.error(errorText(error, "Evidence pack could not be downloaded")); }
  };

  if (loading || !data) return <div className="flex min-h-[50vh] items-center justify-center text-stone-500"><RefreshCw className="mr-2 h-5 w-5 animate-spin" />Checking the tax year…</div>;

  const review = data.review;
  const close = data.close;
  const summary = review.summary;
  const validation = review.validation;
  const isClosed = close.status === "closed";
  const canClose = validation.ready_to_close && (!validation.warning_count || acknowledged);

  return (
    <div className="space-y-6 animate-fade-in" data-testid="tax-year-close-page">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Badge className={isClosed ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-800"} variant="outline">
              {isClosed ? <LockKeyhole className="mr-1 h-3 w-3" /> : <FileCheck2 className="mr-1 h-3 w-3" />}{isClosed ? "Closed and protected" : "Open for review"}
            </Badge>
            <Badge variant="outline" className="border-stone-200 text-stone-600">Cash basis</Badge>
          </div>
          <h1 className="text-3xl font-medium tracking-tight text-stone-900" style={{ fontFamily: "Playfair Display, serif" }}>Tax Year Close</h1>
          <p className="mt-1 max-w-2xl text-sm text-stone-500">Check the figures, resolve anything unusual, then create one permanent accountant-ready evidence pack.</p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Select value={taxYear} onValueChange={setTaxYear}>
            <SelectTrigger className="w-full bg-white sm:w-40" data-testid="tax-year-select"><SelectValue /></SelectTrigger>
            <SelectContent>{taxYears.map((item) => <SelectItem key={item.id} value={item.id}>{item.label}</SelectItem>)}</SelectContent>
          </Select>
          <Button variant="outline" onClick={() => load()}><RefreshCw className="mr-2 h-4 w-4" />Recheck</Button>
          {isClosed ? <Button className="bg-[#1f2933] text-white hover:bg-[#111827]" onClick={downloadPack}><Download className="mr-2 h-4 w-4" />Download evidence pack</Button>
            : <Button className="bg-[#C7A76D] text-white hover:bg-[#B8985E]" disabled={!validation.ready_to_close} onClick={() => { resetDialog(); setCloseOpen(true); }}><LockKeyhole className="mr-2 h-4 w-4" />Close tax year</Button>}
        </div>
      </div>

      <div className="rounded-xl border border-sky-200 bg-sky-50 p-4 text-sm text-sky-950">
        <div className="flex gap-3"><ShieldCheck className="mt-0.5 h-5 w-5 shrink-0" /><div><p className="font-semibold">Preparation and evidence — not direct HMRC submission</p><p className="mt-1 text-sky-800">This produces reliable cash-basis figures, ledgers and supporting files. It does not file a Self Assessment or send an MTD update to HMRC.</p></div></div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card className="border-stone-200"><CardContent className="p-5"><p className="flex items-center gap-2 text-sm text-stone-500"><TrendingUp className="h-4 w-4 text-emerald-600" />Turnover received</p><p className="mt-2 text-2xl font-semibold text-stone-900">{money(summary.turnover)}</p><p className="mt-1 text-xs text-stone-400">Bank {money(summary.bank_income)} · other cash {money(summary.other_cash_income)}</p></CardContent></Card>
        <Card className="border-stone-200"><CardContent className="p-5"><p className="flex items-center gap-2 text-sm text-stone-500"><TrendingDown className="h-4 w-4 text-rose-600" />Allowable expenses</p><p className="mt-2 text-2xl font-semibold text-stone-900">{money(summary.allowable_expenses)}</p><p className="mt-1 text-xs text-stone-400">Includes mileage of {money(summary.mileage)}</p></CardContent></Card>
        <Card className="border-[#C7A76D]/40 bg-[#C7A76D]/5"><CardContent className="p-5"><p className="flex items-center gap-2 text-sm text-[#8a682d]"><PoundSterling className="h-4 w-4" />Net business profit</p><p className="mt-2 text-2xl font-semibold text-stone-900">{money(summary.net_profit)}</p><p className="mt-1 text-xs text-stone-500">The business figure before personal tax calculations</p></CardContent></Card>
      </div>

      <Card className="border-stone-200">
        <CardHeader className="border-b border-stone-100 pb-4"><div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between"><CardTitle className="text-lg">Close checks</CardTitle><div className="flex gap-2"><Badge className={validation.blocker_count ? "bg-rose-100 text-rose-800" : "bg-emerald-100 text-emerald-800"}>{validation.blocker_count} blocking</Badge><Badge className="bg-amber-100 text-amber-800">{validation.warning_count} warnings</Badge></div></div></CardHeader>
        <CardContent className="p-0">
          {validation.checks.length === 0 ? <div className="flex items-center gap-3 p-6 text-emerald-800"><CheckCircle2 className="h-5 w-5" /><span className="font-medium">All checks passed. This year is ready to close.</span></div> : <div className="divide-y divide-stone-100">
            {validation.checks.map((check) => <div key={check.code} className="p-4 sm:p-5"><div className="flex items-start gap-3">
              {check.severity === "blocker" ? <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-rose-600" /> : <TriangleAlert className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />}
              <div className="min-w-0 flex-1"><div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between"><p className="font-semibold text-stone-900">{check.title}</p><p className="text-sm font-medium text-stone-500">{check.count} record{check.count === 1 ? "" : "s"}{check.amount ? ` · ${money(check.amount)}` : ""}</p></div><p className="mt-1 text-sm text-stone-600">{check.guidance}</p>
                {check.examples?.length > 0 && <div className="mt-3 space-y-1 rounded-lg bg-stone-50 p-3 text-xs text-stone-600">{check.examples.map((item, index) => <div key={`${item.id || check.code}-${index}`} className="flex flex-col justify-between gap-1 sm:flex-row"><span className="truncate">{item.date || "No date"} · {item.description || item.client || item.invoice_number || "Record"}</span>{item.amount !== undefined && <span className="shrink-0 font-mono">{money(item.amount)}</span>}</div>)}</div>}
              </div></div></div>)}
          </div>}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
        <Card className="border-stone-200 xl:col-span-3"><CardHeader><CardTitle className="text-lg">Quarterly view</CardTitle></CardHeader><CardContent className="overflow-x-auto p-0 sm:px-6 sm:pb-6"><Table className="min-w-[620px]"><TableHeader><TableRow><TableHead>Quarter</TableHead><TableHead>Period</TableHead><TableHead className="text-right">Income</TableHead><TableHead className="text-right">Expenses</TableHead><TableHead className="text-right">Profit</TableHead></TableRow></TableHeader><TableBody>{review.quarters.map((quarter) => <TableRow key={quarter.name}><TableCell className="font-semibold">{quarter.name}</TableCell><TableCell className="text-stone-500">{quarter.label}</TableCell><TableCell className="text-right font-mono">{money(quarter.income)}</TableCell><TableCell className="text-right font-mono">{money(quarter.expenses)}</TableCell><TableCell className="text-right font-mono font-medium">{money(quarter.profit)}</TableCell></TableRow>)}</TableBody></Table></CardContent></Card>
        <Card className="border-stone-200 xl:col-span-2"><CardHeader><CardTitle className="text-lg">Expense categories</CardTitle></CardHeader><CardContent className="space-y-3">{review.category_summary.length ? review.category_summary.map((item) => <div key={item.category} className="flex items-center justify-between gap-4 border-b border-stone-100 pb-2 text-sm"><span className="text-stone-600">{item.category}</span><span className="font-mono font-medium">{money(item.amount)}</span></div>) : <p className="text-sm text-stone-500">No included expenses in this tax year.</p>}</CardContent></Card>
      </div>

      <Card className="border-stone-200"><CardHeader><div className="flex items-center gap-2"><Archive className="h-5 w-5 text-[#C7A76D]" /><CardTitle className="text-lg">Evidence pack and audit trail</CardTitle></div></CardHeader><CardContent className="space-y-4">
        {isClosed && <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-950"><p className="font-semibold">Version {close.active_version} closed {dateTime(close.closed_at)}</p><p className="mt-1">{close.reason}</p><p className="mt-2 text-xs text-emerald-800">The ZIP contains the annual PDF, CSV ledgers, invoice/payment audit, reconciliation, receipts, invoices, bank statements, checksums and the exact close snapshot.</p></div>}
        {history.length ? <div className="space-y-2">{history.map((item) => <div key={item.id} className="flex flex-col gap-1 rounded-lg bg-stone-50 p-3 text-sm sm:flex-row sm:items-center sm:justify-between"><div><span className="font-semibold capitalize text-stone-800">{item.action}</span><span className="text-stone-500"> · {item.reason}</span></div><span className="shrink-0 text-xs text-stone-400">{dateTime(item.created_at)}</span></div>)}</div> : <p className="text-sm text-stone-500">No close or reopen actions have been recorded yet.</p>}
        {isClosed && <div className="flex flex-col gap-2 border-t border-stone-100 pt-4 sm:flex-row sm:items-center sm:justify-between"><p className="text-xs text-stone-500">Reopening is deliberately audited and never deletes the previously closed evidence pack.</p><Button variant="outline" className="text-amber-800" onClick={() => { resetDialog(); setReopenOpen(true); }}><RotateCcw className="mr-2 h-4 w-4" />Reopen with reason</Button></div>}
      </CardContent></Card>

      <Dialog open={closeOpen} onOpenChange={(open) => { setCloseOpen(open); if (!open) resetDialog(); }}><DialogContent><DialogHeader><DialogTitle>Close tax year {taxYear}</DialogTitle><DialogDescription>This creates a permanent evidence pack and locks this year’s accounts records against accidental edits.</DialogDescription></DialogHeader><div className="space-y-4">
        <div className="space-y-2"><Label htmlFor="close-reason">Reason / close note</Label><Textarea id="close-reason" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="For example: Year checked and ready for accountant" /></div>
        {validation.warning_count > 0 && <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm"><Checkbox checked={acknowledged} onCheckedChange={(value) => setAcknowledged(value === true)} className="mt-0.5" /><span>I have reviewed the {validation.warning_count} warning{validation.warning_count === 1 ? "" : "s"} and want them recorded in the evidence pack.</span></label>}
        <div className="space-y-2"><Label htmlFor="close-confirmation">Type CLOSE {taxYear}</Label><Input id="close-confirmation" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="off" /></div>
      </div><DialogFooter><Button variant="outline" onClick={() => setCloseOpen(false)}>Cancel</Button><Button onClick={closeYear} disabled={working || reason.trim().length < 5 || confirmation !== `CLOSE ${taxYear}` || !canClose} className="bg-[#C7A76D] text-white hover:bg-[#B8985E]">{working ? "Creating pack…" : "Create pack and lock year"}</Button></DialogFooter></DialogContent></Dialog>

      <Dialog open={reopenOpen} onOpenChange={(open) => { setReopenOpen(open); if (!open) resetDialog(); }}><DialogContent><DialogHeader><DialogTitle>Reopen tax year {taxYear}</DialogTitle><DialogDescription>The existing evidence pack stays permanent. Every later change must be checked before you close a new version.</DialogDescription></DialogHeader><div className="space-y-4">
        <div className="space-y-2"><Label htmlFor="reopen-reason">Why is it being reopened?</Label><Textarea id="reopen-reason" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="For example: Correcting a duplicated bank transaction" /></div>
        <div className="space-y-2"><Label htmlFor="reopen-confirmation">Type REOPEN {taxYear}</Label><Input id="reopen-confirmation" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="off" /></div>
      </div><DialogFooter><Button variant="outline" onClick={() => setReopenOpen(false)}>Keep closed</Button><Button onClick={reopenYear} disabled={working || reason.trim().length < 5 || confirmation !== `REOPEN ${taxYear}`} className="bg-amber-700 text-white hover:bg-amber-800">{working ? "Reopening…" : "Reopen and record reason"}</Button></DialogFooter></DialogContent></Dialog>
    </div>
  );
}
