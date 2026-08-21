import { useState, useEffect, useCallback, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Switch } from "@/components/ui/switch";
import { Plus, Trash2, Eye, Pencil, Upload, Loader2, Ban, RotateCcw, ShieldAlert, History } from "lucide-react";
import { formatCurrency } from "@/utils/formatters";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const TAX_YEARS = [
  { id: "2022-23", label: "2022/23" }, { id: "2023-24", label: "2023/24" }, { id: "2024-25", label: "2024/25" },
  { id: "2025-26", label: "2025/26" }, { id: "2026-27", label: "2026/27" },
  { id: "2027-28", label: "2027/28" }, { id: "2028-29", label: "2028/29" },
  { id: "2029-30", label: "2029/30" },
];

function toISO(ukDate) {
  if (!ukDate) return "";
  var p = ukDate.split("/");
  if (p.length === 3) return p[2] + "-" + p[1] + "-" + p[0];
  return ukDate;
}
function toUK(isoDate) {
  if (!isoDate) return "";
  var p = isoDate.split("-");
  if (p.length === 3) return p[2] + "/" + p[1] + "/" + p[0];
  return isoDate;
}

const PdfScanUpload = ({ onScanned, selectedFile, scanResult, onClear }) => {
  const [scanning, setScanning] = useState(false);
  const fileRef = useRef(null);
  const handleScan = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) { toast.error("Please upload a PDF file"); return; }
    setScanning(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await axios.post(`${API}/invoices/scan-pdf`, fd);
      const d = res.data;
      const mapped = {};
      if (d.invoice_number) mapped.invoice_number = d.invoice_number;
      if (d.issue_date) mapped.issue_date = toISO(d.issue_date);
      if (d.couple_names) mapped.couple_names = d.couple_names;
      if (d.total_price !== undefined) mapped.total_price = String(d.total_price);
      if (d.deposit_amount !== undefined) mapped.deposit_amount = String(d.deposit_amount);
      if (d.deposit_paid_date) mapped.deposit_paid_date = toISO(d.deposit_paid_date);
      if (d.final_payment_due) mapped.final_payment_due = toISO(d.final_payment_due);
      if (d.venue) mapped.venue = d.venue;
      if (d.package_name) mapped.package_name = d.package_name;
      if (d.wedding_date) mapped.wedding_date = toISO(d.wedding_date);
      if (d.notes) mapped.notes = d.notes;
      if (d.line_items) mapped.line_items = d.line_items;
      if (d.client_address) mapped.client_address = d.client_address;
      if (d.client_email) mapped.client_email = d.client_email;
      if (d.client_phone) mapped.client_phone = d.client_phone;
      onScanned(mapped, file, d);
      toast.success("PDF read — check every field before importing");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to scan PDF");
    } finally {
      setScanning(false);
      if (!selectedFile && fileRef.current) fileRef.current.value = "";
    }
  };
  return (
    <div className="flex items-center gap-2 p-3 bg-amber-50 border border-amber-200 rounded-md" data-testid="pdf-scan-upload">
      <Upload className="w-4 h-4 text-amber-600 shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-xs text-amber-800 font-medium">Choose a Booking invoice PDF — nothing is saved yet</p>
        {!selectedFile && <input ref={fileRef} type="file" accept=".pdf,application/pdf" onChange={handleScan} className="mt-1 text-xs file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-xs file:bg-amber-100 file:text-amber-800 file:cursor-pointer" data-testid="pdf-scan-file-input" disabled={scanning} />}
        {selectedFile && (
          <div className="mt-1 flex items-center justify-between gap-2">
            <span className="text-xs text-stone-700 truncate">{selectedFile.name}</span>
            <button type="button" onClick={onClear} className="text-xs font-medium text-rose-700 hover:underline">Remove</button>
          </div>
        )}
      </div>
      {scanning && <Loader2 className="w-4 h-4 animate-spin text-amber-600" />}
      {scanResult?.ready_for_review && !scanning && <span className="text-xs font-semibold text-emerald-700">Ready to review</span>}
    </div>
  );
};

const InvoiceForm = ({ formData, setFormData, onSubmit, submitLabel, linked = false, importingPdf = false, showPdfFields = importingPdf, scanResult = null }) => {
  const finalBalance = (parseFloat(formData.total_price) || 0) - (parseFloat(formData.deposit_amount) || 0) - (parseFloat(formData.interim_payment) || 0);
  return (
    <form onSubmit={onSubmit} className="space-y-3">
      {showPdfFields && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 space-y-2" data-testid="invoice-import-review">
          <p className="text-sm font-semibold text-emerald-900">PDF read successfully — review before saving</p>
          <p className="text-xs text-emerald-800">Accounts will recreate the same PDF design with its own next invoice number. The uploaded original is retained privately for duplicate protection and audit history.</p>
          {(scanResult?.warnings || []).map((warning, index) => <p key={index} className="text-xs text-amber-800">• {warning}</p>)}
        </div>
      )}
      {importingPdf && (
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-2">
            <Label>Booking PDF Number</Label>
            <div className="h-9 flex items-center px-3 rounded-md bg-stone-100 border border-stone-200 font-mono text-sm" data-testid="source-invoice-number">
              {formData.invoice_number || "Not found"}
            </div>
            <p className="text-xs text-stone-400">Kept privately; it will not become the Accounts number.</p>
          </div>
          <div className="space-y-2">
            <Label>New Accounts Number</Label>
            <div className="h-9 flex items-center px-3 rounded-md bg-amber-50 border border-amber-200 font-semibold text-sm text-amber-900" data-testid="accounts-number-pending">
              Next available number — assigned on Save
            </div>
          </div>
          <div className="space-y-2 col-span-2">
            <Label>Issue Date</Label>
            <Input type="date" value={formData.issue_date} onChange={(e) => setFormData({ ...formData, issue_date: e.target.value })} className="border-stone-200" data-testid="invoice-issue-date-input" />
          </div>
        </div>
      )}
      {/* Client Details */}
      <div className="space-y-2">
        <Label>Couple Names *</Label>
        <Input value={formData.couple_names} onChange={(e) => setFormData({ ...formData, couple_names: e.target.value })} placeholder="e.g. Sarah & James" required className="border-stone-200" data-testid="couple-names-input" />
      </div>
      <div className="space-y-2">
        <Label>Client Address</Label>
        <Input value={formData.client_address} onChange={(e) => setFormData({ ...formData, client_address: e.target.value })} placeholder="Address" className="border-stone-200" data-testid="client-address-input" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label>Email</Label>
          <Input type="email" value={formData.client_email} onChange={(e) => setFormData({ ...formData, client_email: e.target.value })} placeholder="email@example.com" className="border-stone-200" data-testid="client-email-input" />
        </div>
        <div className="space-y-2">
          <Label>Phone</Label>
          <Input value={formData.client_phone} onChange={(e) => setFormData({ ...formData, client_phone: e.target.value })} placeholder="07..." className="border-stone-200" data-testid="client-phone-input" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label>Wedding Date *</Label>
          <Input type="date" value={formData.wedding_date} onChange={(e) => setFormData({ ...formData, wedding_date: e.target.value })} required className="border-stone-200" data-testid="wedding-date-input" />
        </div>
        <div className="space-y-2">
          <Label>Venue</Label>
          <Input value={formData.venue} onChange={(e) => setFormData({ ...formData, venue: e.target.value })} placeholder="Venue name" className="border-stone-200" data-testid="venue-input" />
        </div>
      </div>
      <div className="space-y-2">
        <Label>Package Name</Label>
        <Input value={formData.package_name} onChange={(e) => setFormData({ ...formData, package_name: e.target.value })} placeholder="e.g. Gold Package 3" className="border-stone-200" data-testid="package-name-input" />
      </div>

      {/* Pricing */}
      <div className="space-y-2">
        <Label>Total Price *</Label>
        <Input type="number" step="0.01" value={formData.total_price} onChange={(e) => setFormData({ ...formData, total_price: e.target.value })} required className="border-stone-200 font-mono" data-testid="total-price-input" />
      </div>

      {/* Payment Schedule */}
      <div className="border border-stone-200 rounded-md p-3 space-y-3">
        <p className="text-xs font-semibold text-stone-500 uppercase tracking-wide">Payment Schedule</p>

        {/* Deposit */}
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label className="text-xs">Deposit Amount</Label>
            <Input type="number" step="0.01" value={formData.deposit_amount} onChange={(e) => setFormData({ ...formData, deposit_amount: e.target.value })} placeholder="0.00" className="border-stone-200 font-mono" data-testid="deposit-input" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Deposit Paid Date</Label>
            <Input type="date" value={formData.deposit_paid_date} onChange={(e) => setFormData({ ...formData, deposit_paid_date: e.target.value })} className="border-stone-200" data-testid="deposit-date-input" />
          </div>
        </div>

        {/* Interim (optional) */}
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label className="text-xs">Interim Payment <span className="text-stone-400">(optional)</span></Label>
            <Input type="number" step="0.01" value={formData.interim_payment} onChange={(e) => setFormData({ ...formData, interim_payment: e.target.value })} placeholder="0.00" className="border-stone-200 font-mono" data-testid="interim-input" />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">Interim Paid Date</Label>
            <Input type="date" value={formData.interim_payment_date} onChange={(e) => setFormData({ ...formData, interim_payment_date: e.target.value })} className="border-stone-200" data-testid="interim-date-input" disabled={!formData.interim_payment || parseFloat(formData.interim_payment) <= 0} />
          </div>
        </div>

        {/* Final Balance — read-only amount + date picker */}
        <div className="border-t border-stone-200 pt-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Final Balance <span className="text-stone-400">(auto)</span></Label>
              <div className="h-9 flex items-center px-3 rounded-md bg-stone-100 border border-stone-200 font-mono text-sm" data-testid="final-balance-display">
                {formatCurrency(finalBalance)}
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Final Balance Paid Date</Label>
              <Input type="date" value={formData.final_payment_paid_date} onChange={(e) => setFormData({ ...formData, final_payment_paid_date: e.target.value })} className="border-stone-200" data-testid="final-paid-date-input" />
            </div>
          </div>
          <p className="text-xs text-stone-400 mt-1">Set the date when the remaining balance was paid. Leave blank if unpaid.</p>
          <div className="space-y-1 mt-3">
            <Label className="text-xs">Final Balance Due Date</Label>
            <Input type="date" value={formData.final_payment_due} onChange={(e) => setFormData({ ...formData, final_payment_due: e.target.value })} className="border-stone-200" data-testid="final-due-date-input" />
            <p className="text-xs text-stone-400">The PDF date is used when importing; otherwise Accounts calculates 45 days before the wedding.</p>
          </div>
        </div>
      </div>

      {/* Notes */}
      <div className="space-y-2">
        <Label>Package Details / Notes</Label>
        <Textarea value={formData.notes} onChange={(e) => setFormData({ ...formData, notes: e.target.value })} placeholder="What's included..." rows={showPdfFields ? 12 : 3} className="border-stone-200" data-testid="notes-input" />
      </div>
      {linked ? (
        <div className="py-2 px-3 bg-teal-50 border border-teal-100 rounded text-xs text-teal-800">
          Booking-linked invoices remain excluded from income totals so bank transactions are not counted twice.
        </div>
      ) : (
        <div className="flex items-center justify-between py-2 px-3 bg-stone-50 rounded">
          <div>
            <Label className="text-sm font-medium text-stone-700">Add to Income</Label>
            <p className="text-xs text-stone-400">Include this invoice amount in income totals (e.g. cash sale)</p>
          </div>
          <Switch checked={formData.include_in_totals} onCheckedChange={(checked) => setFormData({ ...formData, include_in_totals: checked })} data-testid="include-in-totals-switch" />
        </div>
      )}

      {/* Summary */}
      {formData.total_price && (
        <div className="bg-stone-50 rounded p-3 text-sm space-y-1">
          <div className="flex justify-between"><span className="text-stone-500">Total</span><span className="font-mono">{formatCurrency(parseFloat(formData.total_price) || 0)}</span></div>
          <div className="flex justify-between"><span className="text-stone-500">Deposit</span><span className="font-mono">-{formatCurrency(parseFloat(formData.deposit_amount) || 0)}</span></div>
          {parseFloat(formData.interim_payment) > 0 && (<div className="flex justify-between"><span className="text-stone-500">Interim</span><span className="font-mono">-{formatCurrency(parseFloat(formData.interim_payment) || 0)}</span></div>)}
          <div className="flex justify-between border-t border-stone-200 pt-1 font-medium">
            <span className="text-stone-700">Balance Due</span>
            <span className={`font-mono ${finalBalance <= 0 ? "text-emerald-600" : "text-[#C7A76D]"}`}>
              {formatCurrency(finalBalance)}
              {formData.final_payment_paid_date && finalBalance > 0 && <span className="text-emerald-600 text-xs ml-1">(Paid)</span>}
            </span>
          </div>
        </div>
      )}
      <p className="text-xs text-stone-400">Tax years auto-assigned per payment date. {linked ? "This linked invoice is not counted again in income totals." : formData.include_in_totals ? "This invoice WILL be counted in income totals." : "Not counted in income totals unless toggled above."}</p>
      <Button type="submit" disabled={!onSubmit} className="w-full bg-[#C7A76D] hover:bg-[#B8985E] text-white rounded-sm" data-testid="submit-invoice-btn">
        {submitLabel}
      </Button>
    </form>
  );
};

export const Invoices = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [editInvoice, setEditInvoice] = useState(null);
  const [emergencyReason, setEmergencyReason] = useState("");
  const [safetyInvoice, setSafetyInvoice] = useState(null);
  const [safetyAction, setSafetyAction] = useState(null);
  const [safetyReason, setSafetyReason] = useState("");
  const [auditInvoice, setAuditInvoice] = useState(null);
  const [auditLogs, setAuditLogs] = useState([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [filterTaxYear, setFilterTaxYear] = useState(searchParams.get("taxYear") || "all");
  const [searchName, setSearchName] = useState(searchParams.get("search") || "");
  const [sortAlpha, setSortAlpha] = useState(searchParams.get("sort") === "az");
  const emptyForm = { invoice_number: "", issue_date: "", couple_names: "", client_address: "", client_email: "", client_phone: "", wedding_date: "", venue: "", total_price: "", deposit_amount: "", deposit_paid_date: "", interim_payment: "", interim_payment_date: "", final_payment_paid_date: "", final_payment_due: "", package_name: "", notes: "", line_items: [], include_in_totals: false };
  const [formData, setFormData] = useState(emptyForm);
  const [sourcePdf, setSourcePdf] = useState(null);
  const [scanResult, setScanResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const fetchInvoices = useCallback(async () => {
    setLoading(true);
    try {
      const params = filterTaxYear !== "all" ? { tax_year: filterTaxYear } : {};
      const res = await axios.get(`${API}/invoices`, { params });
      setInvoices(res.data);
    } catch { toast.error("Failed to load invoices"); }
    finally { setLoading(false); }
  }, [filterTaxYear]);

  useEffect(() => { fetchInvoices(); }, [fetchInvoices]);

  useEffect(() => {
    if (searchParams.get("action") === "new") setCreateOpen(true);
  }, [searchParams]);

  useEffect(() => {
    const requestedSearch = searchParams.get("search") || "";
    const requestedYear = searchParams.get("taxYear") || "all";
    const requestedSort = searchParams.get("sort") === "az";
    if (requestedSearch !== searchName) setSearchName(requestedSearch);
    if (requestedYear !== filterTaxYear) setFilterTaxYear(requestedYear);
    if (requestedSort !== sortAlpha) setSortAlpha(requestedSort);
    // Browser history can replace all three values at once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    searchName ? next.set("search", searchName) : next.delete("search");
    filterTaxYear !== "all" ? next.set("taxYear", filterTaxYear) : next.delete("taxYear");
    sortAlpha ? next.set("sort", "az") : next.delete("sort");
    setSearchParams(next, { replace: true });
    // The URL deliberately mirrors the current filters for browser Back/Forward and refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchName, filterTaxYear, sortAlpha]);

  const openEdit = (inv) => {
    setEditInvoice(inv);
    setEmergencyReason("");
    setFormData({
      invoice_number: inv.invoice_number || "",
      issue_date: toISO(inv.issue_date || ""),
      couple_names: inv.couple_names || inv.client_name || "",
      client_address: inv.client_address || "",
      client_email: inv.client_email || "",
      client_phone: inv.client_phone || "",
      wedding_date: toISO(inv.wedding_date || inv.date || ""),
      venue: inv.venue || "",
      total_price: String(inv.total_price || inv.amount || ""),
      deposit_amount: String(inv.deposit_amount || ""),
      deposit_paid_date: toISO(inv.deposit_paid_date || ""),
      interim_payment: String(inv.interim_payment || ""),
      interim_payment_date: toISO(inv.interim_payment_date || ""),
      final_payment_paid_date: toISO(inv.final_payment_paid_date || ""),
      final_payment_due: toISO(inv.final_payment_due || ""),
      package_name: inv.package_name || "",
      notes: inv.notes || "",
      line_items: inv.line_items || [],
      include_in_totals: inv.include_in_totals || false,
    });
  };

  const buildPayload = () => ({
    invoice_number: formData.invoice_number || null,
    issue_date: formData.issue_date ? toUK(formData.issue_date) : null,
    couple_names: formData.couple_names,
    client_address: formData.client_address || null,
    client_email: formData.client_email || null,
    client_phone: formData.client_phone || null,
    wedding_date: toUK(formData.wedding_date),
    venue: formData.venue || null,
    total_price: parseFloat(formData.total_price),
    deposit_amount: parseFloat(formData.deposit_amount) || 0,
    deposit_paid_date: formData.deposit_paid_date ? toUK(formData.deposit_paid_date) : null,
    interim_payment: parseFloat(formData.interim_payment) || 0,
    interim_payment_date: formData.interim_payment_date ? toUK(formData.interim_payment_date) : null,
    final_payment_paid_date: formData.final_payment_paid_date ? toUK(formData.final_payment_paid_date) : null,
    final_payment_due: formData.final_payment_due ? toUK(formData.final_payment_due) : null,
    package_name: formData.package_name || null,
    notes: formData.notes || null,
    line_items: formData.line_items || [],
    include_in_totals: formData.include_in_totals,
  });

  const handleCreate = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      if (sourcePdf) {
        const upload = new FormData();
        upload.append("file", sourcePdf);
        upload.append("invoice_json", JSON.stringify(buildPayload()));
        const response = await axios.post(`${API}/invoices/import-pdf`, upload);
        toast.success(`${response.data.invoice_number} created — Accounts copy ready`);
      } else {
        await axios.post(`${API}/invoices`, buildPayload());
        toast.success("Invoice created with PDF");
      }
      setCreateOpen(false);
      setFormData(emptyForm);
      setSourcePdf(null);
      setScanResult(null);
      fetchInvoices();
    } catch (err) { toast.error(err?.response?.data?.detail || "Failed to create invoice"); }
    finally { setSubmitting(false); }
  };

  const handleUpdate = async (e) => {
    e.preventDefault();
    if (!editInvoice) return;
    setSubmitting(true);
    try {
      const linked = editInvoice.source_system === "booking_system";
      if (linked && emergencyReason.trim().length < 5) {
        toast.error("Please enter a clear reason for the Accounts override");
        setSubmitting(false);
        return;
      }
      const endpoint = linked
        ? `${API}/invoices/${editInvoice.id}/emergency-edit`
        : `${API}/invoices/${editInvoice.id}`;
      await axios.put(endpoint, linked ? { ...buildPayload(), reason: emergencyReason.trim() } : buildPayload());
      toast.success(linked ? "Accounts copy updated and safely locked" : editInvoice.source_system === "manual_pdf_import" ? "Accounts details updated — source evidence preserved" : "Invoice updated & PDF regenerated");
      setEditInvoice(null);
      setEmergencyReason("");
      setFormData(emptyForm);
      fetchInvoices();
    } catch (err) { toast.error(err?.response?.data?.detail || "Failed to update invoice"); }
    finally { setSubmitting(false); }
  };

  const openSafetyAction = (inv, action) => {
    setSafetyInvoice(inv);
    setSafetyAction(action);
    setSafetyReason("");
  };

  const handleSafetyAction = async () => {
    if (!safetyInvoice || !safetyAction) return;
    if (safetyReason.trim().length < 5) {
      toast.error("Please enter a clear reason (at least 5 characters)");
      return;
    }
    setSubmitting(true);
    try {
      const route = safetyAction === "restore" ? "restore-booking" : "void";
      await axios.post(`${API}/invoices/${safetyInvoice.id}/${route}`, { reason: safetyReason.trim() });
      toast.success(safetyAction === "restore" ? "Latest Booking values restored" : "Invoice voided in Accounts");
      setSafetyInvoice(null);
      setSafetyAction(null);
      setSafetyReason("");
      fetchInvoices();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Invoice safeguard failed");
    } finally {
      setSubmitting(false);
    }
  };

  const openAuditHistory = async (inv) => {
    setAuditInvoice(inv);
    setAuditLogs([]);
    setAuditLoading(true);
    try {
      const res = await axios.get(`${API}/invoices/${inv.id}/audit`);
      setAuditLogs(res.data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to load invoice history");
    } finally {
      setAuditLoading(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this invoice?")) return;
    try { await axios.delete(`${API}/invoices/${id}`); toast.success("Invoice deleted"); fetchInvoices(); }
    catch { toast.error("Failed to delete invoice"); }
  };

  const handleViewPDF = (id) => { window.open(`${API}/invoices/${id}/pdf`, "_blank"); };

  const getBalance = (inv) => inv.balance_remaining !== undefined
    ? Number(inv.balance_remaining || 0)
    : (inv.total_price || inv.amount || 0) - (inv.deposit_amount || 0) - (inv.interim_payment || 0);
  const getName = (inv) => inv.couple_names || inv.client_name || "-";
  const getTotal = (inv) => inv.total_price || inv.amount || 0;
  const getDate = (inv) => inv.wedding_date || inv.date || "-";
  const getStatus = (inv) => inv.status || (inv.final_payment_paid_date ? "Paid in Full" : inv.deposit_paid_date ? "Deposit Paid" : "Pending");
  const tyLabel = (ty) => { var t = TAX_YEARS.find(x => x.id === ty); return t ? t.label : ty || "-"; };

  const filteredInvoices = invoices
    .filter((inv) => {
      if (!searchName) return true;
      return getName(inv).toLowerCase().includes(searchName.toLowerCase());
    })
    .sort((a, b) => {
      if (!sortAlpha) return 0;
      return getName(a).localeCompare(getName(b));
    });

  return (
    <div className="space-y-6 animate-fade-in" data-testid="invoices-page">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-medium tracking-tight text-stone-900" style={{ fontFamily: 'Playfair Display, serif' }}>Invoices</h1>
          <p className="text-stone-500 mt-1">Track wedding bookings &amp; payments (not counted in income totals)</p>
        </div>
        <div className="flex items-center gap-3">
          <Input value={searchName} onChange={(e) => setSearchName(e.target.value)} placeholder="Search couple..." className="w-40 border-stone-200" data-testid="search-couple-input" />
          <Button variant="outline" size="sm" className={`border-stone-200 ${sortAlpha ? "bg-stone-100" : ""}`} onClick={() => setSortAlpha(!sortAlpha)} data-testid="sort-alpha-btn" title="Sort A-Z">
            {sortAlpha ? "A→Z" : "A-Z"}
          </Button>
          <Select value={filterTaxYear} onValueChange={setFilterTaxYear}>
            <SelectTrigger className="w-36 bg-white border-stone-200" data-testid="filter-tax-year"><SelectValue placeholder="Filter" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Years</SelectItem>
              {TAX_YEARS.map((ty) => (<SelectItem key={ty.id} value={ty.id}>{ty.label}</SelectItem>))}
            </SelectContent>
          </Select>
          <Dialog open={createOpen} onOpenChange={(open) => {
            setCreateOpen(open);
            if (!open) {
              setFormData(emptyForm);
              setSourcePdf(null);
              setScanResult(null);
              const next = new URLSearchParams(searchParams);
              next.delete("action");
              setSearchParams(next, { replace: true });
            }
          }}>
            <DialogTrigger asChild>
              <Button className="bg-[#C7A76D] text-white hover:bg-[#B8985E] rounded-sm" data-testid="add-invoice-btn" onClick={() => { setFormData(emptyForm); setSourcePdf(null); setScanResult(null); }}>
                <Plus className="w-4 h-4 mr-2" />New Invoice
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="create-invoice-dialog">
              <DialogHeader><DialogTitle style={{ fontFamily: 'Playfair Display, serif' }}>{sourcePdf ? "Review & Import Booking Invoice" : "Create New Invoice"}</DialogTitle></DialogHeader>
              <PdfScanUpload
                selectedFile={sourcePdf}
                scanResult={scanResult}
                onScanned={(data, file, result) => {
                  setFormData(prev => ({ ...prev, ...data }));
                  setSourcePdf(file);
                  setScanResult(result);
                }}
                onClear={() => {
                  setSourcePdf(null);
                  setScanResult(null);
                  setFormData(emptyForm);
                }}
              />
              <InvoiceForm
                formData={formData}
                setFormData={setFormData}
                onSubmit={handleCreate}
                importingPdf={!!sourcePdf}
                scanResult={scanResult}
                submitLabel={submitting ? "Saving..." : sourcePdf ? "Create Accounts Invoice" : "Create Invoice & Generate PDF"}
              />
            </DialogContent>
          </Dialog>
        </div>
      </div>

      <Card className="bg-white border-stone-100 card-shadow" data-testid="invoices-table-card">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="border-stone-100">
                <TableHead className="text-stone-500">Invoice</TableHead>
                <TableHead className="text-stone-500">Couple</TableHead>
                <TableHead className="text-stone-500">Wedding</TableHead>
                <TableHead className="text-stone-500">Package</TableHead>
                <TableHead className="text-right text-stone-500">Total</TableHead>
                <TableHead className="text-right text-stone-500">Balance</TableHead>
                <TableHead className="text-stone-500">Status</TableHead>
                <TableHead className="text-right text-stone-500">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow><TableCell colSpan={8} className="text-center py-8 text-stone-400">Loading...</TableCell></TableRow>
              ) : filteredInvoices.length === 0 ? (
                <TableRow><TableCell colSpan={8} className="text-center py-8 text-stone-400">No invoices found.</TableCell></TableRow>
              ) : (
                filteredInvoices.map((inv) => (
                  <TableRow key={inv.id} className={`border-stone-100 ${searchParams.get("focus") === inv.id ? "bg-[#C7A76D]/10" : ""}`} data-testid={`invoice-row-${inv.id}`}>
                    <TableCell className="font-mono text-sm text-[#C7A76D]">{inv.invoice_number || "-"}{inv.source_system === "booking_system" && <span className="block mt-1 text-[10px] font-sans text-teal-700">BOOKING LINKED</span>}{inv.source_system === "manual_pdf_import" && <span className="block mt-1 text-[10px] font-sans text-stone-500">ACCOUNTS COPY</span>}{inv.legacy_invoice_number && inv.legacy_invoice_number !== inv.invoice_number && <span className="block mt-1 text-[10px] font-sans text-stone-500">Previous Studio Ninja: {inv.legacy_invoice_number}</span>}</TableCell>
                    <TableCell className="font-medium">{getName(inv)}</TableCell>
                    <TableCell className="font-mono text-sm">{getDate(inv)}</TableCell>
                    <TableCell className="text-stone-500 text-sm max-w-[180px] truncate">{inv.package_name || (inv.notes ? inv.notes.substring(0, 30) : "-")}</TableCell>
                    <TableCell className="text-right font-mono font-medium">{formatCurrency(getTotal(inv))}</TableCell>
                    <TableCell className="text-right font-mono text-sm">
                      {getBalance(inv) > 0 ? <span className="text-amber-600">{formatCurrency(getBalance(inv))}</span> : <span className="text-emerald-600">{formatCurrency(0)}</span>}
                    </TableCell>
                    <TableCell>
                      <span className={`text-xs px-2 py-1 rounded-sm ${getStatus(inv) === "Paid in Full" ? "bg-emerald-50 text-emerald-700" : getStatus(inv) === "Deposit Paid" ? "bg-amber-50 text-amber-700" : getStatus(inv) === "Interim Paid" ? "bg-blue-50 text-blue-700" : ["void", "cancelled"].includes(String(getStatus(inv)).toLowerCase()) ? "bg-rose-50 text-rose-700" : "bg-stone-100 text-stone-600"}`}>
                        {getStatus(inv)}
                      </span>
                      {inv.include_in_totals && <span className="text-xs px-2 py-1 rounded-sm bg-sky-50 text-sky-700 ml-1">Income</span>}
                      {(inv.total_refunded || 0) > 0 && <span className="text-xs px-2 py-1 rounded-sm bg-rose-50 text-rose-700 ml-1">Refunded {formatCurrency(inv.total_refunded)}</span>}
                      {inv.accounts_override?.active && (
                        <span className="block mt-2 text-[10px] leading-tight text-amber-800" title={inv.accounts_override.reason || "Accounts override active"}>
                          <span className="inline-block px-2 py-1 rounded-sm bg-amber-100 font-semibold">ACCOUNTS OVERRIDE</span>
                          <span className="block mt-1 max-w-[190px] truncate">{inv.accounts_override.reason}</span>
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        {String(getStatus(inv)).toLowerCase() !== "void" && <Button variant="ghost" size="sm" className="h-8 w-8 p-0" onClick={() => openEdit(inv)} title={inv.source_system === "booking_system" ? "Emergency edit Accounts copy" : "Edit"} data-testid={`edit-invoice-${inv.id}`}>
                          <Pencil className="w-4 h-4 text-[#C7A76D]" />
                        </Button>}
                        {inv.file_path && (
                          <Button variant="ghost" size="sm" className="h-8 w-8 p-0" onClick={() => handleViewPDF(inv.id)} title="View PDF" data-testid={`view-pdf-${inv.id}`}>
                            <Eye className="w-4 h-4 text-stone-400" />
                          </Button>
                        )}
                        {inv.source_system !== "booking_system" && <Button variant="ghost" size="sm" className="h-8 w-8 p-0 hover:text-rose-600" onClick={() => handleDelete(inv.id)} title="Delete" data-testid={`delete-invoice-${inv.id}`}>
                          <Trash2 className="w-4 h-4" />
                        </Button>}
                        {!(["void", "cancelled"].includes(String(getStatus(inv)).toLowerCase())) && (
                          <Button variant="ghost" size="sm" className="h-8 w-8 p-0 hover:text-rose-600" onClick={() => openSafetyAction(inv, "void")} title="Void in Accounts" data-testid={`void-invoice-${inv.id}`}>
                            <Ban className="w-4 h-4" />
                          </Button>
                        )}
                        {inv.source_system === "booking_system" && inv.accounts_override?.active && (
                          <Button variant="ghost" size="sm" className="h-8 w-8 p-0 hover:text-teal-700" onClick={() => openSafetyAction(inv, "restore")} title="Restore latest Booking values" data-testid={`restore-invoice-${inv.id}`}>
                            <RotateCcw className="w-4 h-4" />
                          </Button>
                        )}
                        {inv.accounts_override && (
                          <Button variant="ghost" size="sm" className="h-8 w-8 p-0 hover:text-amber-700" onClick={() => openAuditHistory(inv)} title="View safeguard history" data-testid={`invoice-audit-${inv.id}`}>
                            <History className="w-4 h-4" />
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Edit Invoice Dialog */}
      <Dialog open={!!editInvoice} onOpenChange={(open) => { if (!open) { setEditInvoice(null); setEmergencyReason(""); setFormData(emptyForm); } }}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" data-testid="edit-invoice-dialog">
          {editInvoice && (
            <>
              <DialogHeader>
                <DialogTitle style={{ fontFamily: 'Playfair Display, serif' }}>
                  Edit {editInvoice.invoice_number || "Invoice"} — {getName(editInvoice)}
                </DialogTitle>
              </DialogHeader>
              <div className="bg-stone-50 rounded p-3 text-xs space-y-1 mb-2">
                <p className="text-stone-400 font-medium">Payment Tax Years</p>
                <div className="flex justify-between"><span className="text-stone-500">Deposit</span><span>{editInvoice.deposit_paid_date || "Not paid"} {editInvoice.deposit_tax_year ? `· ${tyLabel(editInvoice.deposit_tax_year)}` : ""}</span></div>
                {(editInvoice.interim_payment || 0) > 0 && (
                  <div className="flex justify-between"><span className="text-stone-500">Interim</span><span>{editInvoice.interim_payment_date || "Not paid"} {editInvoice.interim_tax_year ? `· ${tyLabel(editInvoice.interim_tax_year)}` : ""}</span></div>
                )}
                <div className="flex justify-between"><span className="text-stone-500">Balance</span><span>{editInvoice.final_payment_paid_date ? `Paid ${editInvoice.final_payment_paid_date}` : editInvoice.final_payment_due ? `Due ${editInvoice.final_payment_due}` : "TBC"} {editInvoice.final_tax_year ? `· ${tyLabel(editInvoice.final_tax_year)}` : ""}</span></div>
              </div>
              {editInvoice.source_system === "booking_system" && (
                <div className="bg-amber-50 border border-amber-200 rounded-md p-3 space-y-3">
                  <div className="flex gap-2 text-amber-900">
                    <ShieldAlert className="w-4 h-4 mt-0.5 shrink-0" />
                    <div>
                      <p className="text-sm font-semibold">Emergency Accounts override</p>
                      <p className="text-xs mt-1">This changes only the Accounts copy. Future Booking syncs will be safely held behind this override until you choose Restore Booking Values.</p>
                    </div>
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="emergency-edit-reason" className="text-xs">Reason for this change *</Label>
                    <Textarea id="emergency-edit-reason" value={emergencyReason} onChange={(e) => setEmergencyReason(e.target.value)} rows={2} placeholder="For example: correcting an imported total after checking the original invoice" data-testid="emergency-edit-reason" />
                  </div>
                </div>
              )}
              <InvoiceForm formData={formData} setFormData={setFormData} onSubmit={handleUpdate} linked={editInvoice.source_system === "booking_system"} showPdfFields={editInvoice.source_system === "manual_pdf_import"} submitLabel={submitting ? "Saving..." : editInvoice.source_system === "booking_system" ? "Save Accounts Override & Regenerate PDF" : editInvoice.source_system === "manual_pdf_import" ? "Save Details & Preserve Source Evidence" : "Save Changes & Regenerate PDF"} />
            </>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!safetyInvoice} onOpenChange={(open) => { if (!open) { setSafetyInvoice(null); setSafetyAction(null); setSafetyReason(""); } }}>
        <DialogContent className="max-w-md" data-testid="invoice-safety-dialog">
          {safetyInvoice && (
            <>
              <DialogHeader>
                <DialogTitle style={{ fontFamily: 'Playfair Display, serif' }}>
                  {safetyAction === "restore" ? "Restore Booking Values" : "Void Invoice in Accounts"}
                </DialogTitle>
              </DialogHeader>
              <div className={`rounded-md border p-3 text-sm ${safetyAction === "restore" ? "bg-teal-50 border-teal-200 text-teal-900" : "bg-rose-50 border-rose-200 text-rose-900"}`}>
                <p className="font-semibold">{safetyInvoice.invoice_number} — {getName(safetyInvoice)}</p>
                <p className="text-xs mt-1">
                  {safetyAction === "restore"
                    ? "This replaces the Accounts override with the latest Booking values saved during synchronisation."
                    : "This voids only the Accounts copy. It does not alter the Booking system and it sends no email to the couple."}
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="invoice-safety-reason">Reason *</Label>
                <Textarea id="invoice-safety-reason" value={safetyReason} onChange={(e) => setSafetyReason(e.target.value)} rows={4} placeholder={safetyAction === "restore" ? "Why are you restoring the Booking values?" : "Why is this invoice being voided?"} data-testid="invoice-safety-reason" />
                <p className="text-xs text-stone-500">This reason is kept permanently in the invoice audit history.</p>
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => { setSafetyInvoice(null); setSafetyAction(null); setSafetyReason(""); }}>Cancel</Button>
                <Button disabled={submitting} onClick={handleSafetyAction} className={safetyAction === "restore" ? "bg-teal-700 hover:bg-teal-800 text-white" : "bg-rose-700 hover:bg-rose-800 text-white"} data-testid="confirm-invoice-safety-action">
                  {submitting ? "Saving..." : safetyAction === "restore" ? "Restore Booking Values" : "Void in Accounts"}
                </Button>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!auditInvoice} onOpenChange={(open) => { if (!open) { setAuditInvoice(null); setAuditLogs([]); } }}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto" data-testid="invoice-audit-dialog">
          {auditInvoice && (
            <>
              <DialogHeader>
                <DialogTitle style={{ fontFamily: 'Playfair Display, serif' }}>Safeguard History — {auditInvoice.invoice_number}</DialogTitle>
              </DialogHeader>
              {auditLoading ? (
                <p className="py-6 text-center text-stone-500">Loading history...</p>
              ) : auditLogs.length === 0 ? (
                <p className="py-6 text-center text-stone-500">No safeguard changes have been recorded.</p>
              ) : (
                <div className="space-y-3">
                  {auditLogs.map((entry) => (
                    <div key={entry.id} className="border border-stone-200 rounded-md p-3">
                      <div className="flex items-center justify-between gap-3">
                        <span className="text-xs font-semibold uppercase tracking-wide text-amber-800">{String(entry.action || "change").replaceAll("_", " ")}</span>
                        <span className="text-xs text-stone-500">{entry.created_at ? new Date(entry.created_at).toLocaleString("en-GB") : ""}</span>
                      </div>
                      <p className="text-sm text-stone-800 mt-2 whitespace-pre-wrap">{entry.reason}</p>
                      <p className="text-xs text-stone-500 mt-2">Recorded by {entry.admin_email || "administrator"}</p>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default Invoices;
