import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import {
  AlertCircle, Archive, Banknote, CheckCircle2, Download, FileCheck2, LockKeyhole,
  Link2, Pencil, PoundSterling, Receipt, RefreshCw, RotateCcw, ShieldCheck,
  Trash2, TrendingDown, TrendingUp, TriangleAlert, Upload, WalletCards,
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
const EXPENSE_CATEGORIES = [
  "Travel & Mileage", "Equipment & Gear", "Software & Subscriptions",
  "Professional Services", "Marketing & Advertising", "Office & Supplies",
  "Insurance", "Training & Development", "Venue & Location Fees",
  "Utilities", "Bank Fees", "Other",
];
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
  const [searchParams, setSearchParams] = useSearchParams();
  const [taxYears, setTaxYears] = useState([]);
  const [taxYear, setTaxYear] = useState(searchParams.get("year") || getCurrentTaxYear());
  const [data, setData] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [closeOpen, setCloseOpen] = useState(false);
  const [reopenOpen, setReopenOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [cashOpen, setCashOpen] = useState(false);
  const [cashMode, setCashMode] = useState("confirm");
  const [cashPayment, setCashPayment] = useState(null);
  const [cashReason, setCashReason] = useState("");
  const [cashConfirmation, setCashConfirmation] = useState("");
  const [selectedBankPayments, setSelectedBankPayments] = useState([]);
  const [bankMatchOpen, setBankMatchOpen] = useState(false);
  const [bankMatchMode, setBankMatchMode] = useState("create");
  const [bankMatchRecord, setBankMatchRecord] = useState(null);
  const [bankTransactionId, setBankTransactionId] = useState("");
  const [bankMatchReason, setBankMatchReason] = useState("");
  const [bankMatchConfirmation, setBankMatchConfirmation] = useState("");
  const [issueAction, setIssueAction] = useState(null);
  const [issueCategory, setIssueCategory] = useState("");
  const [issueExcluded, setIssueExcluded] = useState(false);
  const [issuePaidPersonally, setIssuePaidPersonally] = useState(false);
  const [issueEquipmentStatus, setIssueEquipmentStatus] = useState("unreviewed");
  const [issueEquipmentNote, setIssueEquipmentNote] = useState("");
  const [issueReceipt, setIssueReceipt] = useState(null);
  const [issueBankId, setIssueBankId] = useState("none");
  const [batchAction, setBatchAction] = useState(null);
  const [batchSelected, setBatchSelected] = useState([]);
  const [batchCategory, setBatchCategory] = useState("");
  const [batchPaidPersonally, setBatchPaidPersonally] = useState(false);

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
  useEffect(() => { setSelectedBankPayments([]); }, [taxYear]);
  useEffect(() => { load(); }, [load]);

  const changeTaxYear = (value) => {
    setTaxYear(value);
    setSearchParams({ year: value });
  };

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
  const openCashAction = (payment, mode) => {
    setCashPayment(payment); setCashMode(mode); setCashReason(""); setCashConfirmation(""); setCashOpen(true);
  };
  const saveCashAction = async () => {
    const endpoint = cashMode === "confirm" ? "confirm" : "revoke";
    setWorking(true);
    try {
      await axios.post(`${API}/tax-year-close/${taxYear}/cash-payments/${endpoint}`, {
        source_invoice_id: cashPayment.source_invoice_id,
        source_payment_id: cashPayment.source_payment_id,
        reason: cashReason,
        confirmation: cashConfirmation,
      });
      toast.success(cashMode === "confirm" ? "Cash payment included once as income" : "Cash confirmation removed");
      setCashOpen(false); await load(true);
    } catch (error) { toast.error(errorText(error, "Cash payment could not be updated")); }
    finally { setWorking(false); }
  };
  const toggleBankPayment = (payment) => {
    setSelectedBankPayments((current) => current.some((item) => item.id === payment.id)
      ? current.filter((item) => item.id !== payment.id)
      : [...current, payment]);
  };
  const openBankMatchCreate = (candidates) => {
    if (selectedBankPayments.length < 2) {
      toast.error("Select at least two Booking payments first");
      return;
    }
    setBankMatchMode("create"); setBankMatchRecord(null);
    setBankTransactionId(candidates.length === 1 ? candidates[0].id : "");
    setBankMatchReason("One bank transfer covers the selected Booking payment entries");
    setBankMatchConfirmation(""); setBankMatchOpen(true);
  };
  const openBankMatchRemove = (match) => {
    setBankMatchMode("remove"); setBankMatchRecord(match); setBankTransactionId("");
    setBankMatchReason(""); setBankMatchConfirmation(""); setBankMatchOpen(true);
  };
  const saveBankMatch = async () => {
    setWorking(true);
    try {
      if (bankMatchMode === "create") {
        await axios.post(`${API}/tax-year-close/${taxYear}/combined-bank-matches`, {
          bank_transaction_id: bankTransactionId,
          payments: selectedBankPayments.map((payment) => ({
            source_invoice_id: payment.source_invoice_id,
            source_payment_id: payment.source_payment_id,
          })),
          reason: bankMatchReason,
          confirmation: bankMatchConfirmation,
        });
        toast.success("Combined bank receipt matched without changing income");
        setSelectedBankPayments([]);
      } else {
        await axios.post(`${API}/tax-year-close/${taxYear}/combined-bank-matches/remove`, {
          match_id: bankMatchRecord.id,
          reason: bankMatchReason,
          confirmation: bankMatchConfirmation,
        });
        toast.success("Combined bank match removed");
      }
      setBankMatchOpen(false); await load(true);
    } catch (error) { toast.error(errorText(error, "Combined bank match could not be updated")); }
    finally { setWorking(false); }
  };

  const issueSource = (record) => record?.source === "manual expense" ? "manual" : record?.source;
  const openIssueRecord = (check, record) => {
    const source = issueSource(record);
    if (source === "bank" && record.transaction_type && record.transaction_type !== "expense") {
      toast.info("Opening Transactions so this bank record keeps its original income/payment type");
      window.location.href = "/transactions";
      return;
    }
    if (!['bank', 'manual'].includes(source)) {
      if (source === "mileage") window.location.href = "/mileage";
      else toast.error("Open the original section to correct this record");
      return;
    }
    setIssueAction({ check, record, source });
    setIssueCategory(record.category || "");
    setIssueExcluded(record.included === false || Boolean(record.excluded_from_totals));
    setIssuePaidPersonally(Boolean(record.paid_personally));
    setIssueEquipmentStatus(record.equipment_review_status || "unreviewed");
    setIssueEquipmentNote(record.equipment_review_note || "");
    setIssueReceipt(null);
    setIssueBankId("none");
  };

  const saveIssueRecord = async () => {
    if (!issueAction) return;
    if (!issueExcluded && !issueCategory) {
      toast.error("Choose an expense category or exclude the record");
      return;
    }
    const { record, source } = issueAction;
    setWorking(true);
    try {
      if (source === "bank") {
        await axios.put(`${API}/transactions/${record.id}`, {
          transaction_type: "expense",
          category: issueCategory || null,
          excluded_from_totals: issueExcluded,
        });
      } else {
        await axios.put(`${API}/expenses/${record.id}`, {
          description: record.description || "Reviewed expense",
          supplier: record.supplier || null,
          category: issueCategory || null,
          include_in_totals: !issueExcluded,
          paid_personally: issuePaidPersonally,
        });
      }

      if (issueReceipt && source === "manual" && !record.receipt_file) {
        const form = new FormData();
        form.append("file", issueReceipt);
        await axios.post(`${API}/expenses/${record.id}/receipt`, form);
      }
      if (issueBankId !== "none" && source === "manual") {
        await axios.post(`${API}/tax-year-close/${taxYear}/expenses/${record.id}/link-bank`, { transaction_id: issueBankId });
      }
      if (issueCategory === "Equipment & Gear" && (
        issueEquipmentStatus !== (record.equipment_review_status || "unreviewed")
        || issueEquipmentNote !== (record.equipment_review_note || "")
      )) {
        await axios.put(`${API}/tax-year-close/${taxYear}/expense-records/${source}/${record.id}/equipment-review`, {
          status: issueEquipmentStatus,
          note: issueEquipmentNote,
        });
      }
      toast.success("Record updated and close checks refreshed");
      setIssueAction(null);
      await load(true);
    } catch (error) {
      toast.error(errorText(error, "The record could not be updated"));
    } finally {
      setWorking(false);
    }
  };

  const deleteIssueRecord = async () => {
    if (!issueAction) return;
    const { record, source } = issueAction;
    if (!window.confirm(`Permanently delete this duplicate record?\n\n${record.description || "Expense"} · ${money(record.amount)}`)) return;
    setWorking(true);
    try {
      await axios.delete(`${API}/${source === "bank" ? "transactions" : "expenses"}/${record.id}`);
      toast.success("Duplicate record deleted and checks refreshed");
      setIssueAction(null);
      await load(true);
    } catch (error) {
      toast.error(errorText(error, "The duplicate could not be deleted"));
    } finally {
      setWorking(false);
    }
  };

  const openBatchEdit = (check, records) => {
    const actionable = records.filter((record) => {
      const source = issueSource(record);
      return source === "manual" || (source === "bank" && (!record.transaction_type || record.transaction_type === "expense"));
    });
    setBatchAction({ check, records: actionable });
    setBatchSelected(actionable.map((record) => `${issueSource(record)}:${record.id}`));
    setBatchCategory("");
    setBatchPaidPersonally(false);
  };

  const toggleBatchRecord = (key) => setBatchSelected((current) => current.includes(key)
    ? current.filter((item) => item !== key)
    : [...current, key]);

  const saveBatchEdit = async () => {
    if (!batchAction || !batchCategory || batchSelected.length === 0) return;
    setWorking(true);
    try {
      const selected = batchAction.records.filter((record) => batchSelected.includes(`${issueSource(record)}:${record.id}`));
      await Promise.all(selected.map((record) => {
        const source = issueSource(record);
        if (source === "bank") {
          return axios.put(`${API}/transactions/${record.id}`, {
            transaction_type: "expense",
            category: batchCategory,
            excluded_from_totals: record.included === false,
          });
        }
        return axios.put(`${API}/expenses/${record.id}`, {
          description: record.description || "Reviewed expense",
          supplier: record.supplier || null,
          category: batchCategory,
          include_in_totals: record.included !== false,
          paid_personally: batchPaidPersonally ? true : Boolean(record.paid_personally),
        });
      }));
      toast.success(`${selected.length} records updated and checks refreshed`);
      setBatchAction(null);
      await load(true);
    } catch (error) {
      toast.error(errorText(error, "The batch update could not be completed"));
      await load(true);
    } finally {
      setWorking(false);
    }
  };

  if (loading || !data) return <div className="flex min-h-[50vh] items-center justify-center text-stone-500"><RefreshCw className="mr-2 h-5 w-5 animate-spin" />Checking the tax year…</div>;

  const review = data.review;
  const close = data.close;
  const summary = review.summary;
  const validation = review.validation;
  const isClosed = close.status === "closed";
  const canClose = validation.ready_to_close && (!validation.warning_count || acknowledged);
  const reconciliation = review.booking_reconciliation || {};
  const unmatchedPayments = reconciliation.unmatched_rows || [];
  const cashPayments = reconciliation.cash_rows || [];
  const combinedMatches = reconciliation.combined_matches || [];
  const selectedBankTotal = selectedBankPayments.reduce((total, payment) => total + Number(payment.amount || 0), 0);
  const suitableBankCandidates = (reconciliation.bank_match_candidates || []).filter(
    (transaction) => Math.abs(Number(transaction.amount || 0) - selectedBankTotal) < 0.009
  );

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
          <Select value={taxYear} onValueChange={changeTaxYear}>
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
        <CardHeader className="border-b border-stone-100 pb-4"><div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between"><div><CardTitle className="text-lg">Close Checks Action Centre</CardTitle><p className="mt-1 text-sm text-stone-500">Open the affected record here, make the decision, and the checks refresh automatically.</p></div><div className="flex gap-2"><Badge className={validation.blocker_count ? "bg-rose-100 text-rose-800" : "bg-emerald-100 text-emerald-800"}>{validation.blocker_count} blocking</Badge><Badge className="bg-amber-100 text-amber-800">{validation.warning_count} warnings</Badge></div></div></CardHeader>
        <CardContent className="p-0">
          {validation.checks.length === 0 ? <div className="flex items-center gap-3 p-6 text-emerald-800"><CheckCircle2 className="h-5 w-5" /><span className="font-medium">All checks passed. This year is ready to close.</span></div> : <div className="divide-y divide-stone-100">
            {validation.checks.map((check) => {
              const records = check.records || check.examples || [];
              return <div key={check.code} className="p-4 sm:p-5"><div className="flex items-start gap-3">
                {check.severity === "blocker" ? <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-rose-600" /> : <TriangleAlert className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />}
                <div className="min-w-0 flex-1"><div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between"><p className="font-semibold text-stone-900">{check.title}</p><div className="flex flex-wrap items-center gap-2"><p className="text-sm font-medium text-stone-500">{check.count} record{check.count === 1 ? "" : "s"}{check.amount ? ` · ${money(check.amount)}` : ""}</p>{check.code === "uncategorised_expenses" && records.length > 1 && !isClosed && <Button size="sm" variant="outline" className="h-8 bg-white" onClick={() => openBatchEdit(check, records)}>Batch categorise</Button>}</div></div><p className="mt-1 text-sm text-stone-600">{check.guidance}</p>
                  {records.length > 0 && <div className="mt-3 max-h-80 space-y-2 overflow-y-auto">{records.map((item, index) => {
                    const source = issueSource(item);
                    const actionable = ["bank", "manual", "mileage"].includes(source);
                    const actionLabel = check.code === "capital_items_review" ? "Review treatment" : check.code === "missing_receipts" ? "Attach receipt" : check.code.includes("duplicate") ? "Resolve duplicate" : "Review & fix";
                    return <div key={`${item.id || check.code}-${index}`} className="flex flex-col gap-3 rounded-lg border border-stone-200 bg-stone-50 p-3 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0"><p className="truncate text-sm font-medium text-stone-800">{item.description || item.client || item.invoice_number || "Record"}</p><p className="mt-0.5 text-xs text-stone-500">{item.date || "No date"}{item.amount !== undefined ? ` · ${money(item.amount)}` : ""}{source === "manual" ? " · Manual expense" : source === "bank" ? " · Bank record" : source === "mileage" ? " · Mileage" : ""}</p>{item.equipment_review_status === "flag_capital" && <p className="mt-1 text-xs font-medium text-amber-700">Flagged for accountant/capital review</p>}</div>
                      {actionable && !isClosed && <Button size="sm" variant="outline" className="shrink-0 bg-white" onClick={() => openIssueRecord(check, item)}><Pencil className="mr-2 h-3.5 w-3.5" />{actionLabel}</Button>}
                      {isClosed && <Badge className="shrink-0 bg-stone-200 text-stone-700">Reopen year to change</Badge>}
                    </div>;
                  })}</div>}
                </div></div></div>;
            })}
          </div>}
        </CardContent>
      </Card>

      <Card className="border-stone-200">
        <CardHeader className="border-b border-stone-100 pb-4"><div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between"><div><CardTitle className="flex items-center gap-2 text-lg"><Banknote className="h-5 w-5 text-[#C7A76D]" />Booking payment reconciliation</CardTitle><p className="mt-1 text-sm text-stone-500">Match normal transfers automatically, link several Booking entries to one combined bank receipt, or confirm genuine cash.</p></div><div className="flex flex-wrap gap-2"><Badge className="bg-emerald-100 text-emerald-800">{reconciliation.matched || 0} bank matched</Badge><Badge className="bg-violet-100 text-violet-800">{combinedMatches.length} combined</Badge><Badge className="bg-sky-100 text-sky-800">{reconciliation.confirmed_cash || 0} cash</Badge><Badge className="bg-amber-100 text-amber-800">{reconciliation.unmatched || 0} unmatched</Badge></div></div></CardHeader>
        <CardContent className="p-0">
          {combinedMatches.length > 0 && <div className="border-b border-stone-100 p-4 sm:p-5">
            <p className="mb-3 text-sm font-semibold text-stone-800">Combined bank receipts</p>
            <div className="max-h-72 space-y-2 overflow-y-auto">{combinedMatches.map((match) => <div key={match.id} className="flex flex-col gap-3 rounded-lg border border-violet-100 bg-violet-50 p-3 sm:flex-row sm:items-center sm:justify-between">
              <div><p className="font-medium text-stone-900">{match.bank_description || "Bank receipt"} · {money(match.bank_amount)}</p><p className="text-sm text-stone-600">{match.bank_date} · matched to {match.payments?.length || 0} Booking payments</p><p className="mt-1 text-xs text-stone-500">{match.payments?.map((payment) => `${payment.invoice_number} ${money(payment.amount)}`).join(" + ")}</p></div>
              {!isClosed && <Button size="sm" variant="outline" onClick={() => openBankMatchRemove(match)}>Undo combined match</Button>}
            </div>)}</div>
          </div>}
          {cashPayments.length > 0 && <div className="border-b border-stone-100 p-4 sm:p-5"><p className="mb-3 text-sm font-semibold text-stone-800">Confirmed cash income</p><div className="max-h-72 space-y-2 overflow-y-auto">{cashPayments.map((payment) => <div key={payment.id} className="flex flex-col gap-3 rounded-lg border border-sky-100 bg-sky-50 p-3 sm:flex-row sm:items-center sm:justify-between"><div><p className="font-medium text-stone-900">{payment.invoice_number} · {payment.description}</p><p className="text-sm text-stone-600">{payment.date} · {money(payment.amount)} · Cash received</p><p className="mt-1 text-xs text-stone-500">{payment.confirmation_reason}</p></div>{!isClosed && payment.confirmation_id && <Button size="sm" variant="outline" onClick={() => openCashAction(payment, "revoke")}>Undo cash confirmation</Button>}</div>)}</div></div>}
          {unmatchedPayments.length > 0 ? <div className="p-4 sm:p-5">
            <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-sm font-semibold text-stone-800">Payments needing a decision</p><p className="mt-1 text-xs text-stone-500">For one combined bank receipt, tick every Booking payment included in it.</p></div>{selectedBankPayments.length > 0 && <div className="flex flex-col gap-2 sm:items-end"><p className="text-sm font-medium text-stone-700">{selectedBankPayments.length} selected · {money(selectedBankTotal)}</p><Button size="sm" disabled={isClosed || selectedBankPayments.length < 2 || suitableBankCandidates.length === 0} onClick={() => openBankMatchCreate(suitableBankCandidates)} className="bg-violet-700 text-white hover:bg-violet-800">Match to one bank receipt</Button>{selectedBankPayments.length >= 2 && suitableBankCandidates.length === 0 && <p className="text-xs text-amber-700">No unused bank receipt equals {money(selectedBankTotal)}</p>}</div>}</div>
            <div className="max-h-96 space-y-2 overflow-y-auto">{unmatchedPayments.map((payment) => <div key={payment.id} className={`flex flex-col gap-3 rounded-lg border p-3 sm:flex-row sm:items-center sm:justify-between ${selectedBankPayments.some((item) => item.id === payment.id) ? "border-violet-300 bg-violet-50" : "border-amber-200 bg-amber-50"}`}>
              <div className="flex min-w-0 items-start gap-3"><Checkbox checked={selectedBankPayments.some((item) => item.id === payment.id)} disabled={isClosed} onCheckedChange={() => toggleBankPayment(payment)} className="mt-1" /><div><p className="font-medium text-stone-900">{payment.invoice_number} · {payment.description}</p><p className="text-sm text-stone-600">{payment.date} · {money(payment.amount)} · no bank match</p></div></div>
              <Button size="sm" disabled={isClosed} className="bg-[#C7A76D] text-white hover:bg-[#B8985E]" onClick={() => openCashAction(payment, "confirm")}>Confirm cash received</Button>
            </div>)}</div>
          </div> : cashPayments.length === 0 && <div className="flex items-center gap-3 p-6 text-emerald-800"><CheckCircle2 className="h-5 w-5" /><span className="font-medium">Every Booking payment is reconciled.</span></div>}
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

      <Dialog open={Boolean(issueAction)} onOpenChange={(open) => { if (!open) setIssueAction(null); }}>
        <DialogContent className="max-h-[92vh] max-w-xl overflow-y-auto" data-testid="close-check-action-dialog">
          <DialogHeader><DialogTitle>Review and resolve this record</DialogTitle><DialogDescription>{issueAction?.check?.title}</DialogDescription></DialogHeader>
          {issueAction && <div className="space-y-4">
            <div className="rounded-lg border border-stone-200 bg-stone-50 p-4">
              <div className="flex items-start justify-between gap-3"><div><p className="font-semibold text-stone-900">{issueAction.record.description || "Expense record"}</p><p className="mt-1 text-sm text-stone-500">{issueAction.record.date || "No date"} · {issueAction.source === "bank" ? "Bank statement" : "Manual expense"}</p></div><strong className="shrink-0 font-mono text-rose-700">{money(issueAction.record.amount)}</strong></div>
            </div>

            <div className="space-y-2"><Label>Expense category</Label><Select value={issueCategory} onValueChange={setIssueCategory} disabled={issueExcluded}><SelectTrigger><SelectValue placeholder="Choose the correct category" /></SelectTrigger><SelectContent>{EXPENSE_CATEGORIES.map((category) => <SelectItem key={category} value={category}>{category}</SelectItem>)}</SelectContent></Select></div>

            <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-stone-200 p-3 text-sm"><Checkbox checked={issueExcluded} onCheckedChange={(value) => setIssueExcluded(value === true)} className="mt-0.5" /><span><strong className="block text-stone-800">Exclude from tax totals</strong><span className="text-stone-500">Use this only when the item is personal, a transfer, duplicated elsewhere, or should not form part of the business totals.</span></span></label>

            {issueAction.source === "manual" && <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-emerald-200 bg-emerald-50/50 p-3 text-sm"><Checkbox checked={issuePaidPersonally} onCheckedChange={(value) => setIssuePaidPersonally(value === true)} className="mt-0.5" /><span><strong className="flex items-center gap-2 text-stone-800"><WalletCards className="h-4 w-4" />Paid personally / personal credit card</strong><span className="text-stone-500">Keep this genuine business expense in the totals without matching it to the business bank.</span></span></label>}

            {issueAction.source === "manual" && !issueAction.record.receipt_file && <div className="space-y-2 rounded-lg border border-sky-200 bg-sky-50 p-3"><Label className="flex items-center gap-2"><Upload className="h-4 w-4" />Attach the missing receipt</Label><Input type="file" accept=".pdf,.png,.jpg,.jpeg,.webp" onChange={(event) => setIssueReceipt(event.target.files?.[0] || null)} /><p className="text-xs text-sky-800">Optional: the original PDF or photograph will be included in the evidence pack.</p></div>}

            {issueAction.record.bank_candidates?.length > 0 && issueAction.source === "manual" && <div className="space-y-2 rounded-lg border border-violet-200 bg-violet-50 p-3"><Label className="flex items-center gap-2"><Link2 className="h-4 w-4" />Link to the matching business-bank payment</Label><Select value={issueBankId} onValueChange={setIssueBankId}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">Do not link</SelectItem>{issueAction.record.bank_candidates.map((candidate) => <SelectItem key={candidate.id} value={candidate.id}>{candidate.date} · {candidate.description} · {money(candidate.amount)}</SelectItem>)}</SelectContent></Select><p className="text-xs text-violet-800">Linking keeps this receipt as evidence but counts the bank payment only once.</p></div>}

            {issueCategory === "Equipment & Gear" && <div className="space-y-3 rounded-lg border border-amber-200 bg-amber-50 p-3"><div><Label>Equipment review decision</Label><p className="mt-1 text-xs text-amber-800">This records your review; it does not make a tax decision for you.</p></div><Select value={issueEquipmentStatus} onValueChange={setIssueEquipmentStatus}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="unreviewed">Still needs review</SelectItem><SelectItem value="keep_current">Reviewed — keep current treatment</SelectItem><SelectItem value="flag_capital">Flag for accountant / capital review</SelectItem></SelectContent></Select><Textarea value={issueEquipmentNote} onChange={(event) => setIssueEquipmentNote(event.target.value)} placeholder="Optional private review note" /></div>}

            <div className="flex flex-col-reverse gap-2 border-t border-stone-100 pt-4 sm:flex-row sm:justify-between">
              {issueAction.check.code.includes("duplicate") ? <Button variant="outline" className="border-rose-200 text-rose-700 hover:bg-rose-50" disabled={working} onClick={deleteIssueRecord}><Trash2 className="mr-2 h-4 w-4" />Delete duplicate</Button> : <span />}
              <div className="flex gap-2"><Button variant="outline" onClick={() => setIssueAction(null)}>Cancel</Button><Button disabled={working || (!issueExcluded && !issueCategory)} onClick={saveIssueRecord} className="bg-[#C7A76D] text-white hover:bg-[#B8985E]"><Receipt className="mr-2 h-4 w-4" />{working ? "Saving…" : "Save and recheck"}</Button></div>
            </div>
          </div>}
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(batchAction)} onOpenChange={(open) => { if (!open) setBatchAction(null); }}>
        <DialogContent className="max-h-[92vh] max-w-xl overflow-y-auto" data-testid="batch-expense-review-dialog">
          <DialogHeader><DialogTitle>Batch categorise similar records</DialogTitle><DialogDescription>Select the records that belong in the same expense category. Nothing is deleted or excluded.</DialogDescription></DialogHeader>
          {batchAction && <div className="space-y-4">
            <div className="max-h-64 space-y-2 overflow-y-auto rounded-lg border border-stone-200 p-2">
              {batchAction.records.map((record) => {
                const key = `${issueSource(record)}:${record.id}`;
                return <label key={key} className="flex cursor-pointer items-start gap-3 rounded-md p-2 hover:bg-stone-50"><Checkbox checked={batchSelected.includes(key)} onCheckedChange={() => toggleBatchRecord(key)} className="mt-1" /><span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium text-stone-800">{record.description || "Expense"}</span><span className="text-xs text-stone-500">{record.date || "No date"} · {money(record.amount)} · {issueSource(record) === "bank" ? "Bank" : "Manual"}</span></span></label>;
              })}
            </div>
            <div className="space-y-2"><Label>Apply this category to {batchSelected.length} selected record{batchSelected.length === 1 ? "" : "s"}</Label><Select value={batchCategory} onValueChange={setBatchCategory}><SelectTrigger><SelectValue placeholder="Choose the shared category" /></SelectTrigger><SelectContent>{EXPENSE_CATEGORIES.map((category) => <SelectItem key={category} value={category}>{category}</SelectItem>)}</SelectContent></Select></div>
            {batchAction.records.some((record) => issueSource(record) === "manual") && <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-emerald-200 bg-emerald-50/50 p-3 text-sm"><Checkbox checked={batchPaidPersonally} onCheckedChange={(value) => setBatchPaidPersonally(value === true)} className="mt-0.5" /><span><strong className="block text-stone-800">Mark selected manual records as paid personally</strong><span className="text-stone-500">Leave unticked to preserve each record’s existing payment source.</span></span></label>}
            <DialogFooter><Button variant="outline" onClick={() => setBatchAction(null)}>Cancel</Button><Button className="bg-[#C7A76D] text-white hover:bg-[#B8985E]" disabled={working || !batchCategory || batchSelected.length === 0} onClick={saveBatchEdit}>{working ? "Saving…" : `Update ${batchSelected.length} records`}</Button></DialogFooter>
          </div>}
        </DialogContent>
      </Dialog>

      <Dialog open={closeOpen} onOpenChange={(open) => { setCloseOpen(open); if (!open) resetDialog(); }}><DialogContent><DialogHeader><DialogTitle>Close tax year {taxYear}</DialogTitle><DialogDescription>This creates a permanent evidence pack and locks this year’s accounts records against accidental edits.</DialogDescription></DialogHeader><div className="space-y-4">
        <div className="space-y-2"><Label htmlFor="close-reason">Reason / close note</Label><Textarea id="close-reason" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="For example: Year checked and ready for accountant" /></div>
        {validation.warning_count > 0 && <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm"><Checkbox checked={acknowledged} onCheckedChange={(value) => setAcknowledged(value === true)} className="mt-0.5" /><span>I have reviewed the {validation.warning_count} warning{validation.warning_count === 1 ? "" : "s"} and want them recorded in the evidence pack.</span></label>}
        <div className="space-y-2"><Label htmlFor="close-confirmation">Type CLOSE {taxYear}</Label><Input id="close-confirmation" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="off" /></div>
      </div><DialogFooter><Button variant="outline" onClick={() => setCloseOpen(false)}>Cancel</Button><Button onClick={closeYear} disabled={working || reason.trim().length < 5 || confirmation !== `CLOSE ${taxYear}` || !canClose} className="bg-[#C7A76D] text-white hover:bg-[#B8985E]">{working ? "Creating pack…" : "Create pack and lock year"}</Button></DialogFooter></DialogContent></Dialog>

      <Dialog open={reopenOpen} onOpenChange={(open) => { setReopenOpen(open); if (!open) resetDialog(); }}><DialogContent><DialogHeader><DialogTitle>Reopen tax year {taxYear}</DialogTitle><DialogDescription>The existing evidence pack stays permanent. Every later change must be checked before you close a new version.</DialogDescription></DialogHeader><div className="space-y-4">
        <div className="space-y-2"><Label htmlFor="reopen-reason">Why is it being reopened?</Label><Textarea id="reopen-reason" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="For example: Correcting a duplicated bank transaction" /></div>
        <div className="space-y-2"><Label htmlFor="reopen-confirmation">Type REOPEN {taxYear}</Label><Input id="reopen-confirmation" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="off" /></div>
      </div><DialogFooter><Button variant="outline" onClick={() => setReopenOpen(false)}>Keep closed</Button><Button onClick={reopenYear} disabled={working || reason.trim().length < 5 || confirmation !== `REOPEN ${taxYear}`} className="bg-amber-700 text-white hover:bg-amber-800">{working ? "Reopening…" : "Reopen and record reason"}</Button></DialogFooter></DialogContent></Dialog>

      <Dialog open={cashOpen} onOpenChange={setCashOpen}><DialogContent><DialogHeader><DialogTitle>{cashMode === "confirm" ? "Confirm cash received" : "Undo cash confirmation"}</DialogTitle><DialogDescription>{cashPayment ? `${cashPayment.invoice_number} · ${cashPayment.description} · ${money(cashPayment.amount)} received ${cashPayment.date}` : "Booking payment"}</DialogDescription></DialogHeader><div className="space-y-4">
        <div className="rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900">{cashMode === "confirm" ? "Use this only when the money was genuinely handed to you in cash. It will be counted once as income without a bank match." : "The payment will return to the unmatched list. The correction remains recorded in the audit history."}</div>
        <div className="space-y-2"><Label htmlFor="cash-reason">Private audit note</Label><Textarea id="cash-reason" value={cashReason} onChange={(event) => setCashReason(event.target.value)} placeholder={cashMode === "confirm" ? "For example: Final balance paid in cash at the wedding" : "Why is the cash confirmation being removed?"} /></div>
        <div className="space-y-2"><Label htmlFor="cash-confirmation">Type {cashMode === "confirm" ? "CONFIRM CASH" : "REMOVE CASH"}</Label><Input id="cash-confirmation" value={cashConfirmation} onChange={(event) => setCashConfirmation(event.target.value)} autoComplete="off" /></div>
      </div><DialogFooter><Button variant="outline" onClick={() => setCashOpen(false)}>Cancel</Button><Button onClick={saveCashAction} disabled={working || cashReason.trim().length < 5 || cashConfirmation !== (cashMode === "confirm" ? "CONFIRM CASH" : "REMOVE CASH")} className={cashMode === "confirm" ? "bg-[#C7A76D] text-white hover:bg-[#B8985E]" : "bg-amber-700 text-white hover:bg-amber-800"}>{working ? "Saving…" : cashMode === "confirm" ? "Count as cash income" : "Remove confirmation"}</Button></DialogFooter></DialogContent></Dialog>

      <Dialog open={bankMatchOpen} onOpenChange={setBankMatchOpen}><DialogContent><DialogHeader><DialogTitle>{bankMatchMode === "create" ? "Match combined bank receipt" : "Undo combined bank match"}</DialogTitle><DialogDescription>{bankMatchMode === "create" ? `${selectedBankPayments.length} Booking payments total ${money(selectedBankTotal)}.` : `${bankMatchRecord?.bank_description || "Bank receipt"} · ${money(bankMatchRecord?.bank_amount)}`}</DialogDescription></DialogHeader><div className="space-y-4">
        <div className="rounded-lg border border-violet-200 bg-violet-50 p-3 text-sm text-violet-950">{bankMatchMode === "create" ? "This links several Booking payment entries to one real bank receipt. It does not add income, create cash or alter the invoice." : "The payments will return to the unmatched list. The original bank income remains unchanged and the action stays in the audit trail."}</div>
        {bankMatchMode === "create" && <>
          <div className="space-y-2"><Label>Selected Booking payments</Label><div className="space-y-1 rounded-lg border border-stone-200 bg-stone-50 p-3 text-sm">{selectedBankPayments.map((payment) => <div key={payment.id} className="flex justify-between gap-3"><span>{payment.invoice_number} · {payment.description}</span><span className="shrink-0 font-mono">{money(payment.amount)}</span></div>)}<div className="mt-2 flex justify-between border-t border-stone-200 pt-2 font-semibold"><span>Total</span><span className="font-mono">{money(selectedBankTotal)}</span></div></div></div>
          <div className="space-y-2"><Label htmlFor="combined-bank-transaction">Matching bank receipt</Label><Select value={bankTransactionId} onValueChange={setBankTransactionId}><SelectTrigger id="combined-bank-transaction"><SelectValue placeholder="Choose the bank receipt" /></SelectTrigger><SelectContent>{suitableBankCandidates.map((transaction) => <SelectItem key={transaction.id} value={transaction.id}>{transaction.date} · {transaction.description} · {money(transaction.amount)}</SelectItem>)}</SelectContent></Select></div>
        </>}
        <div className="space-y-2"><Label htmlFor="bank-match-reason">Private audit note</Label><Textarea id="bank-match-reason" value={bankMatchReason} onChange={(event) => setBankMatchReason(event.target.value)} placeholder={bankMatchMode === "create" ? "Why do these payments belong to this one receipt?" : "Why is this match being removed?"} /></div>
        <div className="space-y-2"><Label htmlFor="bank-match-confirmation">Type {bankMatchMode === "create" ? "MATCH BANK" : "REMOVE BANK MATCH"}</Label><Input id="bank-match-confirmation" value={bankMatchConfirmation} onChange={(event) => setBankMatchConfirmation(event.target.value)} autoComplete="off" /></div>
      </div><DialogFooter><Button variant="outline" onClick={() => setBankMatchOpen(false)}>Cancel</Button><Button onClick={saveBankMatch} disabled={working || bankMatchReason.trim().length < 5 || (bankMatchMode === "create" && !bankTransactionId) || bankMatchConfirmation !== (bankMatchMode === "create" ? "MATCH BANK" : "REMOVE BANK MATCH")} className="bg-violet-700 text-white hover:bg-violet-800">{working ? "Saving…" : bankMatchMode === "create" ? "Match without changing income" : "Remove combined match"}</Button></DialogFooter></DialogContent></Dialog>
    </div>
  );
}
