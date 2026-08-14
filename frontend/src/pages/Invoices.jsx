import { useState, useEffect, useCallback, useRef } from "react";
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
import { Plus, Trash2, Eye, Pencil, Upload, Loader2 } from "lucide-react";
import { formatCurrency } from "@/utils/formatters";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const TAX_YEARS = [
  { id: "2023-24", label: "2023/24" }, { id: "2024-25", label: "2024/25" },
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

const PdfScanUpload = ({ onScanned }) => {
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
      if (d.couple_names) mapped.couple_names = d.couple_names;
      if (d.total_price) mapped.total_price = String(d.total_price);
      if (d.deposit_amount) mapped.deposit_amount = String(d.deposit_amount);
      if (d.venue) mapped.venue = d.venue;
      if (d.package_name) mapped.package_name = d.package_name;
      if (d.wedding_date) mapped.wedding_date = toISO(d.wedding_date);
      if (d.notes) mapped.notes = d.notes;
      if (d.client_address) mapped.client_address = d.client_address;
      if (d.client_email) mapped.client_email = d.client_email;
      if (d.client_phone) mapped.client_phone = d.client_phone;
      onScanned(mapped);
      toast.success("PDF scanned — form pre-filled");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to scan PDF");
    } finally {
      setScanning(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };
  return (
    <div className="flex items-center gap-2 p-3 bg-amber-50 border border-amber-200 rounded-md" data-testid="pdf-scan-upload">
      <Upload className="w-4 h-4 text-amber-600 shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-xs text-amber-800 font-medium">Scan an existing invoice PDF to pre-fill the form</p>
        <input ref={fileRef} type="file" accept=".pdf" onChange={handleScan} className="mt-1 text-xs file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-xs file:bg-amber-100 file:text-amber-800 file:cursor-pointer" data-testid="pdf-scan-file-input" disabled={scanning} />
      </div>
      {scanning && <Loader2 className="w-4 h-4 animate-spin text-amber-600" />}
    </div>
  );
};

const InvoiceForm = ({ formData, setFormData, onSubmit, submitLabel }) => {
  const finalBalance = (parseFloat(formData.total_price) || 0) - (parseFloat(formData.deposit_amount) || 0) - (parseFloat(formData.interim_payment) || 0);
  return (
    <form onSubmit={onSubmit} className="space-y-3">
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
        </div>
      </div>

      {/* Notes */}
      <div className="space-y-2">
        <Label>Package Details / Notes</Label>
        <Textarea value={formData.notes} onChange={(e) => setFormData({ ...formData, notes: e.target.value })} placeholder="What's included..." rows={3} className="border-stone-200" data-testid="notes-input" />
      </div>
      <div className="flex items-center justify-between py-2 px-3 bg-stone-50 rounded">
        <div>
          <Label className="text-sm font-medium text-stone-700">Add to Income</Label>
          <p className="text-xs text-stone-400">Include this invoice amount in income totals (e.g. cash sale)</p>
        </div>
        <Switch checked={formData.include_in_totals} onCheckedChange={(checked) => setFormData({ ...formData, include_in_totals: checked })} data-testid="include-in-totals-switch" />
      </div>

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
      <p className="text-xs text-stone-400">Tax years auto-assigned per payment date. {formData.include_in_totals ? "This invoice WILL be counted in income totals." : "Not counted in income totals unless toggled above."}</p>
      <Button type="submit" disabled={!onSubmit} className="w-full bg-[#C7A76D] hover:bg-[#B8985E] text-white rounded-sm" data-testid="submit-invoice-btn">
        {submitLabel}
      </Button>
    </form>
  );
};

export const Invoices = () => {
  const [invoices, setInvoices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [editInvoice, setEditInvoice] = useState(null);
  const [filterTaxYear, setFilterTaxYear] = useState("all");
  const [searchName, setSearchName] = useState("");
  const [sortAlpha, setSortAlpha] = useState(false);
  const emptyForm = { couple_names: "", client_address: "", client_email: "", client_phone: "", wedding_date: "", venue: "", total_price: "", deposit_amount: "", deposit_paid_date: "", interim_payment: "", interim_payment_date: "", final_payment_paid_date: "", package_name: "", notes: "", include_in_totals: false };
  const [formData, setFormData] = useState(emptyForm);
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

  const openEdit = (inv) => {
    setEditInvoice(inv);
    setFormData({
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
      package_name: inv.package_name || "",
      notes: inv.notes || "",
      include_in_totals: inv.include_in_totals || false,
    });
  };

  const buildPayload = () => ({
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
    package_name: formData.package_name || null,
    notes: formData.notes || null,
    include_in_totals: formData.include_in_totals,
  });

  const handleCreate = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await axios.post(`${API}/invoices`, buildPayload());
      toast.success("Invoice created with PDF");
      setCreateOpen(false);
      setFormData(emptyForm);
      fetchInvoices();
    } catch { toast.error("Failed to create invoice"); }
    finally { setSubmitting(false); }
  };

  const handleUpdate = async (e) => {
    e.preventDefault();
    if (!editInvoice) return;
    setSubmitting(true);
    try {
      await axios.put(`${API}/invoices/${editInvoice.id}`, buildPayload());
      toast.success("Invoice updated & PDF regenerated");
      setEditInvoice(null);
      setFormData(emptyForm);
      fetchInvoices();
    } catch { toast.error("Failed to update invoice"); }
    finally { setSubmitting(false); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this invoice?")) return;
    try { await axios.delete(`${API}/invoices/${id}`); toast.success("Invoice deleted"); fetchInvoices(); }
    catch { toast.error("Failed to delete invoice"); }
  };

  const handleViewPDF = (id) => { window.open(`${API}/invoices/${id}/pdf`, "_blank"); };

  const getBalance = (inv) => (inv.total_price || inv.amount || 0) - (inv.deposit_amount || 0) - (inv.interim_payment || 0);
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
          <Dialog open={createOpen} onOpenChange={setCreateOpen}>
            <DialogTrigger asChild>
              <Button className="bg-[#C7A76D] text-white hover:bg-[#B8985E] rounded-sm" data-testid="add-invoice-btn" onClick={() => setFormData(emptyForm)}>
                <Plus className="w-4 h-4 mr-2" />New Invoice
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto" data-testid="create-invoice-dialog">
              <DialogHeader><DialogTitle style={{ fontFamily: 'Playfair Display, serif' }}>Create New Invoice</DialogTitle></DialogHeader>
              <PdfScanUpload onScanned={(data) => setFormData(prev => ({ ...prev, ...data }))} />
              <InvoiceForm formData={formData} setFormData={setFormData} onSubmit={handleCreate} submitLabel={submitting ? "Saving..." : "Create Invoice & Generate PDF"} />
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
                  <TableRow key={inv.id} className="border-stone-100" data-testid={`invoice-row-${inv.id}`}>
                    <TableCell className="font-mono text-sm text-[#C7A76D]">{inv.invoice_number || "-"}</TableCell>
                    <TableCell className="font-medium">{getName(inv)}</TableCell>
                    <TableCell className="font-mono text-sm">{getDate(inv)}</TableCell>
                    <TableCell className="text-stone-500 text-sm max-w-[180px] truncate">{inv.package_name || (inv.notes ? inv.notes.substring(0, 30) : "-")}</TableCell>
                    <TableCell className="text-right font-mono font-medium">{formatCurrency(getTotal(inv))}</TableCell>
                    <TableCell className="text-right font-mono text-sm">
                      {getBalance(inv) > 0 ? <span className="text-amber-600">{formatCurrency(getBalance(inv))}</span> : <span className="text-emerald-600">{formatCurrency(0)}</span>}
                    </TableCell>
                    <TableCell>
                      <span className={`text-xs px-2 py-1 rounded-sm ${getStatus(inv) === "Paid in Full" ? "bg-emerald-50 text-emerald-700" : getStatus(inv) === "Deposit Paid" ? "bg-amber-50 text-amber-700" : getStatus(inv) === "Interim Paid" ? "bg-blue-50 text-blue-700" : "bg-stone-100 text-stone-600"}`}>
                        {getStatus(inv)}
                      </span>
                      {inv.include_in_totals && <span className="text-xs px-2 py-1 rounded-sm bg-sky-50 text-sky-700 ml-1">Income</span>}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button variant="ghost" size="sm" className="h-8 w-8 p-0" onClick={() => openEdit(inv)} title="Edit" data-testid={`edit-invoice-${inv.id}`}>
                          <Pencil className="w-4 h-4 text-[#C7A76D]" />
                        </Button>
                        {inv.file_path && (
                          <Button variant="ghost" size="sm" className="h-8 w-8 p-0" onClick={() => handleViewPDF(inv.id)} title="View PDF" data-testid={`view-pdf-${inv.id}`}>
                            <Eye className="w-4 h-4 text-stone-400" />
                          </Button>
                        )}
                        <Button variant="ghost" size="sm" className="h-8 w-8 p-0 hover:text-rose-600" onClick={() => handleDelete(inv.id)} title="Delete" data-testid={`delete-invoice-${inv.id}`}>
                          <Trash2 className="w-4 h-4" />
                        </Button>
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
      <Dialog open={!!editInvoice} onOpenChange={(open) => { if (!open) { setEditInvoice(null); setFormData(emptyForm); } }}>
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
              <InvoiceForm formData={formData} setFormData={setFormData} onSubmit={handleUpdate} submitLabel={submitting ? "Saving..." : "Save Changes & Regenerate PDF"} />
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default Invoices;
