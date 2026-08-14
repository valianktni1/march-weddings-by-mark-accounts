import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Plus, Receipt, Trash2, Eye, Upload, FileText, RefreshCw } from "lucide-react";
import { formatCurrency, formatDateUK, getCurrentTaxYear, fromInputDate } from "@/utils/formatters";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const TAX_YEARS = [
  { id: "2024-25", label: "2024/25" },
  { id: "2025-26", label: "2025/26" },
  { id: "2026-27", label: "2026/27" },
  { id: "2027-28", label: "2027/28" },
  { id: "2028-29", label: "2028/29" },
  { id: "2029-30", label: "2029/30" },
];

const EXPENSE_CATEGORIES = [
  "Travel & Mileage", "Equipment & Gear", "Software & Subscriptions",
  "Professional Services", "Marketing & Advertising", "Office & Supplies",
  "Insurance", "Training & Development", "Venue & Location Fees",
  "Utilities", "Bank Fees", "Other"
];

function calcTaxYear(ukDate) {
  if (!ukDate) return getCurrentTaxYear();
  var p = ukDate.split("/");
  if (p.length !== 3) return getCurrentTaxYear();
  var year = parseInt(p[2]), month = parseInt(p[1]), day = parseInt(p[0]);
  var start = year;
  if (month < 4 || (month === 4 && day <= 5)) start = year - 1;
  var end = (start + 1) % 100;
  return start + "-" + (end < 10 ? "0" + end : end);
}

function ukToISO(ukDate) {
  if (!ukDate) return "";
  var p = ukDate.split("/");
  if (p.length === 3) return p[2] + "-" + p[1] + "-" + p[0];
  return ukDate;
}

export const Expenses = () => {
  const [expenses, setExpenses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [filterTaxYear, setFilterTaxYear] = useState("all");
  const [scanning, setScanning] = useState(false);
  const [formData, setFormData] = useState({
    description: "", amount: "", category: "", date: new Date().toISOString().split("T")[0],
    tax_year: getCurrentTaxYear(), supplier: "", include_amount: true,
  });
  const [file, setFile] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [templateOpen, setTemplateOpen] = useState(false);
  const [newTemplate, setNewTemplate] = useState({ description: "", amount: "", category: "", supplier: "" });

  const fetchExpenses = useCallback(async () => {
    setLoading(true);
    try {
      const params = filterTaxYear !== "all" ? { tax_year: filterTaxYear } : {};
      const res = await axios.get(`${API}/expenses`, { params });
      setExpenses(res.data);
    } catch { toast.error("Failed to load expenses"); }
    finally { setLoading(false); }
  }, [filterTaxYear]);

  const fetchTemplates = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/recurring-expenses`);
      setTemplates(res.data);
    } catch {}
  }, []);

  useEffect(() => { fetchExpenses(); }, [fetchExpenses]);
  useEffect(() => { fetchTemplates(); }, [fetchTemplates]);

  const handleScanPDF = async (selectedFile) => {
    if (!selectedFile || !selectedFile.name.toLowerCase().endsWith(".pdf")) return;
    setScanning(true);
    try {
      const fd = new FormData();
      fd.append("file", selectedFile);
      const res = await axios.post(`${API}/expenses/scan-pdf`, fd);
      const d = res.data;
      setFormData(prev => ({
        ...prev,
        description: d.description || prev.description,
        amount: d.amount ? String(d.amount) : prev.amount,
        supplier: d.supplier || prev.supplier,
        date: d.date ? ukToISO(d.date) : prev.date,
        tax_year: d.date ? calcTaxYear(d.date) : prev.tax_year,
      }));
      toast.success("PDF scanned — fields pre-filled");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Could not scan PDF");
    } finally { setScanning(false); }
  };

  const handleFileChange = (e) => {
    const f = e.target.files?.[0] || null;
    setFile(f);
    if (f && f.name.toLowerCase().endsWith(".pdf")) {
      handleScanPDF(f);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const fd = new FormData();
      fd.append("description", formData.description);
      fd.append("amount", formData.amount);
      fd.append("category", formData.category);
      fd.append("date", fromInputDate(formData.date));
      fd.append("tax_year", formData.tax_year);
      fd.append("include_amount", formData.include_amount.toString());
      if (formData.supplier) fd.append("supplier", formData.supplier);

      if (file) {
        fd.append("file", file);
        await axios.post(`${API}/expenses/upload`, fd);
      } else {
        await axios.post(`${API}/expenses`, {
          ...formData, amount: parseFloat(formData.amount), date: fromInputDate(formData.date),
        });
      }
      toast.success("Expense added");
      setDialogOpen(false);
      setFormData({ description: "", amount: "", category: "", date: new Date().toISOString().split("T")[0], tax_year: getCurrentTaxYear(), supplier: "", include_amount: true });
      setFile(null);
      fetchExpenses();
    } catch { toast.error("Failed to add expense"); }
    finally { setSubmitting(false); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this expense?")) return;
    try { await axios.delete(`${API}/expenses/${id}`); toast.success("Expense deleted"); fetchExpenses(); }
    catch { toast.error("Failed to delete expense"); }
  };

  const handleViewFile = (id) => { window.open(`${API}/expenses/${id}/file`, "_blank"); };

  const handleCreateTemplate = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API}/recurring-expenses`, newTemplate);
      toast.success("Template saved");
      setNewTemplate({ description: "", amount: "", category: "", supplier: "" });
      setTemplateOpen(false);
      fetchTemplates();
    } catch { toast.error("Failed to save template"); }
  };

  const handleUseTemplate = async (templateId) => {
    try {
      const today = new Date();
      const day = String(today.getDate()).padStart(2, "0");
      const month = String(today.getMonth() + 1).padStart(2, "0");
      const year = today.getFullYear();
      const dateStr = `${day}/${month}/${year}`;
      await axios.post(`${API}/recurring-expenses/${templateId}/create`, { date: dateStr, tax_year: getCurrentTaxYear() });
      toast.success("Expense created from template");
      fetchExpenses();
    } catch { toast.error("Failed to create expense"); }
  };

  const handleDeleteTemplate = async (id) => {
    if (!window.confirm("Delete this template?")) return;
    try { await axios.delete(`${API}/recurring-expenses/${id}`); toast.success("Template deleted"); fetchTemplates(); }
    catch { toast.error("Failed to delete"); }
  };

  const totalAmount = expenses.reduce((sum, exp) => sum + (exp.amount || 0), 0);
  const expensesByCategory = expenses.reduce((acc, exp) => {
    const cat = exp.category || "Other";
    acc[cat] = (acc[cat] || 0) + (exp.amount || 0);
    return acc;
  }, {});

  return (
    <div className="space-y-6 animate-fade-in" data-testid="expenses-page">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-medium tracking-tight text-stone-900" style={{ fontFamily: 'Playfair Display, serif' }}>Expenses</h1>
          <p className="text-stone-500 mt-1">Track your business expenses</p>
        </div>
        <div className="flex items-center gap-3">
          <Select value={filterTaxYear} onValueChange={setFilterTaxYear}>
            <SelectTrigger className="w-36 bg-white border-stone-200" data-testid="filter-tax-year"><SelectValue placeholder="Filter" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Years</SelectItem>
              {TAX_YEARS.map((ty) => (<SelectItem key={ty.id} value={ty.id}>{ty.label}</SelectItem>))}
            </SelectContent>
          </Select>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button className="bg-[#C7A76D] text-white hover:bg-[#B8985E] rounded-sm" data-testid="add-expense-btn">
                <Plus className="w-4 h-4 mr-2" />Add Expense
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto" data-testid="add-expense-dialog">
              <DialogHeader>
                <DialogTitle style={{ fontFamily: 'Playfair Display, serif' }}>Add New Expense</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleSubmit} className="space-y-4">
                {/* PDF Upload & Scan */}
                <div className="space-y-2">
                  <Label>Attach Receipt/Invoice (PDF/Image)</Label>
                  <div className="relative">
                    <Input type="file" accept=".pdf,.jpg,.jpeg,.png" onChange={handleFileChange} className="border-stone-200" data-testid="expense-file-input" />
                    {scanning && <p className="text-xs text-[#C7A76D] mt-1 animate-pulse">Scanning PDF for details...</p>}
                  </div>
                  <p className="text-xs text-stone-400">Upload a PDF invoice to auto-fill fields below (free, no credits)</p>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Category *</Label>
                    <Select value={formData.category} onValueChange={(v) => setFormData({ ...formData, category: v })}>
                      <SelectTrigger className="border-stone-200" data-testid="expense-category-select"><SelectValue placeholder="Select" /></SelectTrigger>
                      <SelectContent>
                        {EXPENSE_CATEGORIES.map((cat) => (<SelectItem key={cat} value={cat}>{cat}</SelectItem>))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Tax Year *</Label>
                    <Select value={formData.tax_year} onValueChange={(v) => setFormData({ ...formData, tax_year: v })}>
                      <SelectTrigger className="border-stone-200" data-testid="expense-tax-year-select"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {TAX_YEARS.map((ty) => (<SelectItem key={ty.id} value={ty.id}>{ty.label}</SelectItem>))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label>Description *</Label>
                  <Textarea value={formData.description} onChange={(e) => setFormData({ ...formData, description: e.target.value })} placeholder="e.g. Adobe Photography Plan" required className="border-stone-200" data-testid="expense-description-input" />
                </div>
                <div className="space-y-2">
                  <Label>Supplier</Label>
                  <Input value={formData.supplier} onChange={(e) => setFormData({ ...formData, supplier: e.target.value })} placeholder="e.g. Adobe, Amazon" className="border-stone-200" data-testid="expense-supplier-input" />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Amount (*) *</Label>
                    <Input type="number" step="0.01" value={formData.amount} onChange={(e) => setFormData({ ...formData, amount: e.target.value })} placeholder="0.00" required className="border-stone-200 font-mono" data-testid="expense-amount-input" />
                  </div>
                  <div className="space-y-2">
                    <Label>Date *</Label>
                    <Input type="date" value={formData.date} onChange={(e) => setFormData({ ...formData, date: e.target.value })} required className="border-stone-200" data-testid="expense-date-input" />
                  </div>
                </div>
                <div className="flex items-center space-x-2 p-3 bg-stone-50 rounded-sm border border-stone-100">
                  <Checkbox id="include_amount" checked={formData.include_amount} onCheckedChange={(checked) => setFormData({ ...formData, include_amount: !!checked })} data-testid="include-amount-checkbox" />
                  <Label htmlFor="include_amount" className="text-sm text-stone-600 cursor-pointer">Include amount in expense totals</Label>
                </div>
                <Button type="submit" disabled={submitting} className="w-full bg-[#C7A76D] hover:bg-[#B8985E] text-white rounded-sm" data-testid="submit-expense-btn">
                  {submitting ? "Adding..." : file ? "Add Expense & Store Receipt" : "Add Expense"}
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="bg-white border-stone-100 card-shadow md:col-span-1" data-testid="expenses-summary">
          <CardContent className="py-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-sm bg-rose-50 flex items-center justify-center">
                <Receipt className="w-5 h-5 text-rose-600" />
              </div>
              <div>
                <p className="text-sm text-stone-500">{expenses.length} Expenses</p>
                <p className="text-xl font-mono font-medium text-rose-700" data-testid="total-expenses-amount">{formatCurrency(totalAmount)}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-white border-stone-100 card-shadow md:col-span-3">
          <CardHeader className="pb-2"><CardTitle className="text-sm text-stone-500">By Category</CardTitle></CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-3">
              {Object.entries(expensesByCategory).sort(([,a],[,b]) => b - a).slice(0,6).map(([cat, amt]) => (
                <div key={cat} className="px-3 py-2 bg-stone-50 rounded-sm border border-stone-100">
                  <p className="text-xs text-stone-500">{cat}</p>
                  <p className="font-mono text-sm text-stone-700">{formatCurrency(amt)}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Recurring Templates */}
      {templates.length > 0 && (
        <Card className="bg-white border-stone-100 card-shadow" data-testid="recurring-templates-card">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm text-stone-500 flex items-center gap-2"><RefreshCw className="w-3 h-3" /> Recurring Expenses — Quick Add</CardTitle>
              <Dialog open={templateOpen} onOpenChange={setTemplateOpen}>
                <DialogTrigger asChild>
                  <Button variant="ghost" size="sm" className="text-xs text-stone-400 hover:text-stone-600" data-testid="new-template-btn"><Plus className="w-3 h-3 mr-1" />New Template</Button>
                </DialogTrigger>
                <DialogContent className="max-w-sm">
                  <DialogHeader><DialogTitle>Create Recurring Template</DialogTitle></DialogHeader>
                  <form onSubmit={handleCreateTemplate} className="space-y-3">
                    <div className="space-y-2"><Label>Description *</Label><Input value={newTemplate.description} onChange={e => setNewTemplate({...newTemplate, description: e.target.value})} placeholder="e.g. BRSK Broadband" required className="border-stone-200" data-testid="template-desc" /></div>
                    <div className="grid grid-cols-2 gap-3">
                      <div className="space-y-2"><Label>Amount *</Label><Input type="number" step="0.01" value={newTemplate.amount} onChange={e => setNewTemplate({...newTemplate, amount: e.target.value})} required className="border-stone-200 font-mono" data-testid="template-amount" /></div>
                      <div className="space-y-2"><Label>Category</Label>
                        <Select value={newTemplate.category} onValueChange={v => setNewTemplate({...newTemplate, category: v})}>
                          <SelectTrigger className="border-stone-200"><SelectValue placeholder="Select" /></SelectTrigger>
                          <SelectContent>{EXPENSE_CATEGORIES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                        </Select>
                      </div>
                    </div>
                    <div className="space-y-2"><Label>Supplier</Label><Input value={newTemplate.supplier} onChange={e => setNewTemplate({...newTemplate, supplier: e.target.value})} className="border-stone-200" data-testid="template-supplier" /></div>
                    <Button type="submit" className="w-full bg-[#C7A76D] hover:bg-[#B8985E] text-white rounded-sm" data-testid="save-template-btn">Save Template</Button>
                  </form>
                </DialogContent>
              </Dialog>
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {templates.map(t => (
                <div key={t.id} className="flex items-center gap-2 px-3 py-2 bg-stone-50 rounded border border-stone-100" data-testid={"template-" + t.id}>
                  <div className="flex-1 min-w-0">
                    <span className="text-sm text-stone-700">{t.description}</span>
                    <span className="text-xs font-mono text-stone-400 ml-2">{formatCurrency(t.amount)}</span>
                  </div>
                  <Button size="sm" variant="outline" className="h-7 text-xs border-[#C7A76D] text-[#C7A76D] hover:bg-[#C7A76D]/10" onClick={() => handleUseTemplate(t.id)} data-testid={"use-template-" + t.id}>
                    <Plus className="w-3 h-3 mr-1" />Add
                  </Button>
                  <Button size="sm" variant="ghost" className="h-7 w-7 p-0 text-stone-300 hover:text-rose-500" onClick={() => handleDeleteTemplate(t.id)} data-testid={"delete-template-" + t.id}>
                    <Trash2 className="w-3 h-3" />
                  </Button>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* First-time template prompt */}
      {templates.length === 0 && (
        <div className="flex items-center justify-between px-4 py-3 bg-stone-50 rounded border border-stone-100">
          <p className="text-sm text-stone-500"><RefreshCw className="w-3 h-3 inline mr-1" />Got recurring expenses? Set up templates for one-click monthly entries.</p>
          <Dialog open={templateOpen} onOpenChange={setTemplateOpen}>
            <DialogTrigger asChild>
              <Button variant="outline" size="sm" className="text-xs border-stone-200" data-testid="setup-template-btn"><Plus className="w-3 h-3 mr-1" />Create Template</Button>
            </DialogTrigger>
            <DialogContent className="max-w-sm">
              <DialogHeader><DialogTitle>Create Recurring Template</DialogTitle></DialogHeader>
              <form onSubmit={handleCreateTemplate} className="space-y-3">
                <div className="space-y-2"><Label>Description *</Label><Input value={newTemplate.description} onChange={e => setNewTemplate({...newTemplate, description: e.target.value})} placeholder="e.g. BRSK Broadband" required className="border-stone-200" data-testid="template-desc-new" /></div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2"><Label>Amount *</Label><Input type="number" step="0.01" value={newTemplate.amount} onChange={e => setNewTemplate({...newTemplate, amount: e.target.value})} required className="border-stone-200 font-mono" data-testid="template-amount-new" /></div>
                  <div className="space-y-2"><Label>Category</Label>
                    <Select value={newTemplate.category} onValueChange={v => setNewTemplate({...newTemplate, category: v})}>
                      <SelectTrigger className="border-stone-200"><SelectValue placeholder="Select" /></SelectTrigger>
                      <SelectContent>{EXPENSE_CATEGORIES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="space-y-2"><Label>Supplier</Label><Input value={newTemplate.supplier} onChange={e => setNewTemplate({...newTemplate, supplier: e.target.value})} className="border-stone-200" data-testid="template-supplier-new" /></div>
                <Button type="submit" className="w-full bg-[#C7A76D] hover:bg-[#B8985E] text-white rounded-sm" data-testid="save-template-btn-new">Save Template</Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>
      )}

      <Card className="bg-white border-stone-100 card-shadow" data-testid="expenses-table-card">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="border-stone-100">
                <TableHead className="text-stone-500">Date</TableHead>
                <TableHead className="text-stone-500">Description</TableHead>
                <TableHead className="text-stone-500">Supplier</TableHead>
                <TableHead className="text-stone-500">Category</TableHead>
                <TableHead className="text-stone-500">Tax Year</TableHead>
                <TableHead className="text-right text-stone-500">Amount</TableHead>
                <TableHead className="text-right text-stone-500">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow><TableCell colSpan={7} className="text-center py-8 text-stone-400">Loading...</TableCell></TableRow>
              ) : expenses.length === 0 ? (
                <TableRow><TableCell colSpan={7} className="text-center py-8 text-stone-400">No expenses found.</TableCell></TableRow>
              ) : (
                expenses.map((exp) => (
                  <TableRow key={exp.id} className="border-stone-100" data-testid={`expense-row-${exp.id}`}>
                    <TableCell className="font-mono text-sm">{formatDateUK(exp.date)}</TableCell>
                    <TableCell className="font-medium max-w-xs truncate">{exp.description}</TableCell>
                    <TableCell className="text-stone-500 text-sm">{exp.supplier || "-"}</TableCell>
                    <TableCell><span className="text-xs px-2 py-1 bg-rose-50 text-rose-700 rounded-sm">{exp.category}</span></TableCell>
                    <TableCell><span className="text-xs px-2 py-1 bg-stone-100 rounded-sm">{TAX_YEARS.find(t => t.id === exp.tax_year)?.label || exp.tax_year}</span></TableCell>
                    <TableCell className="text-right font-mono font-medium text-rose-700">
                      {exp.amount === 0 ? <span className="text-stone-400">(not included)</span> : formatCurrency(exp.amount)}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        {exp.file_path && (
                          <Button variant="ghost" size="sm" className="h-8 w-8 p-0" onClick={() => handleViewFile(exp.id)} title="View Receipt" data-testid={`view-expense-${exp.id}`}>
                            <Eye className="w-4 h-4 text-stone-400" />
                          </Button>
                        )}
                        <Button variant="ghost" size="sm" className="h-8 w-8 p-0 hover:text-rose-600" onClick={() => handleDelete(exp.id)} title="Delete" data-testid={`delete-expense-${exp.id}`}>
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
    </div>
  );
};

export default Expenses;
