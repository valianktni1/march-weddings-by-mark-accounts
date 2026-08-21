import { useState, useEffect, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { 
  TrendingUp, 
  TrendingDown, 
  Wallet, 
  FileText, 
  Receipt, 
  ArrowLeftRight,
  Download,
  Upload,
  RefreshCw,
  HardDrive,
  CalendarClock,
  Clock3,
  ChevronRight
} from "lucide-react";
import { formatCurrency, getCurrentTaxYear } from "@/utils/formatters";
import { OverdueAlerts, MonthlyChart, CategoryChart, ComparisonCard } from "./DashboardCharts";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const TAX_YEARS = [
  { id: "2023-24", label: "2023/24" },
  { id: "2024-25", label: "2024/25" },
  { id: "2025-26", label: "2025/26" },
  { id: "2026-27", label: "2026/27" },
  { id: "2027-28", label: "2027/28" },
  { id: "2028-29", label: "2028/29" },
  { id: "2029-30", label: "2029/30" },
];

export const Dashboard = () => {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [taxYear, setTaxYear] = useState(searchParams.get("taxYear") || getCurrentTaxYear());
  const [summary, setSummary] = useState(null);
  const [extras, setExtras] = useState(null);
  const [comparison, setComparison] = useState(null);
  const [loading, setLoading] = useState(true);
  const [backupLoading, setBackupLoading] = useState(false);
  const [restoreLoading, setRestoreLoading] = useState(false);
  const [recent, setRecent] = useState([]);
  const [cashPreview, setCashPreview] = useState(null);

  const getPrevTaxYear = (ty) => {
    try {
      const start = parseInt(ty.split("-")[0]);
      return `${start - 1}-${String(start).slice(2)}`;
    } catch { return null; }
  };

  const fetchSummary = useCallback(async () => {
    setLoading(true);
    try {
      const [summaryRes, extrasRes] = await Promise.all([
        axios.get(`${API}/summary/${taxYear}`),
        axios.get(`${API}/dashboard-extras/${taxYear}`)
      ]);
      setSummary(summaryRes.data);
      setExtras(extrasRes.data);

      const prevYear = getPrevTaxYear(taxYear);
      if (prevYear) {
        try {
          const prevRes = await axios.get(`${API}/summary/${prevYear}`);
          setComparison(prevRes.data);
        } catch { setComparison(null); }
      }
    } catch (error) {
      console.error("Failed to fetch summary:", error);
      toast.error("Failed to load summary");
    } finally {
      setLoading(false);
    }
  }, [taxYear]);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  useEffect(() => {
    const requestedYear = searchParams.get("taxYear") || getCurrentTaxYear();
    if (requestedYear !== taxYear) setTaxYear(requestedYear);
  }, [searchParams, taxYear]);

  useEffect(() => {
    Promise.all([axios.get(`${API}/recent-records?limit=6`), axios.get(`${API}/cash-flow?horizon_days=30`)])
      .then(([recentRes, cashRes]) => { setRecent(recentRes.data); setCashPreview(cashRes.data); })
      .catch(() => { /* The main dashboard remains usable if a preview fails. */ });
  }, []);

  const changeTaxYear = (value) => {
    setTaxYear(value);
    const next = new URLSearchParams(searchParams);
    next.set("taxYear", value);
    setSearchParams(next, { replace: true });
  };

  const handleBackup = async () => {
    setBackupLoading(true);
    try {
      const response = await axios.post(`${API}/backup`);
      const totals = response.data.totals || {};
      const msg = `Backed up: ${totals.transactions || 0} transactions, ${totals.invoices || 0} invoices, ${totals.expenses || 0} expenses, ${totals.bank_statements || 0} statements`;
      toast.success(msg);
      // Auto-download the zip
      window.location.href = `${API}/backup/download/${response.data.backup_name}.zip`;
    } catch (error) {
      console.error("Backup failed:", error);
      toast.error("Backup failed: " + (error.response?.data?.detail || error.message));
    } finally {
      setBackupLoading(false);
    }
  };

  const handleRestore = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setRestoreLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      
      await axios.post(`${API}/restore`, formData);
      toast.success("Data restored successfully!");
      fetchSummary();
    } catch (error) {
      console.error("Restore failed:", error);
      toast.error("Restore failed: " + (error.response?.data?.detail || error.message));
    } finally {
      setRestoreLoading(false);
      event.target.value = '';
    }
  };

  return (
    <div className="space-y-8 animate-fade-in" data-testid="dashboard">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-4xl font-medium tracking-tight text-stone-900" style={{ fontFamily: 'Playfair Display, serif' }}>
            Financial Overview
          </h1>
          <p className="text-stone-500 mt-1">Weddings by Mark — UK Sole Trader Accounts</p>
        </div>
        
        {/* Tax Year Selector */}
        <div className="flex items-center gap-3">
          <span className="text-sm text-stone-500">Tax Year:</span>
          <Select value={taxYear} onValueChange={changeTaxYear} data-testid="tax-year-selector">
            <SelectTrigger className="w-36 bg-white border-stone-200" data-testid="tax-year-trigger">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TAX_YEARS.map((ty) => (
                <SelectItem key={ty.id} value={ty.id} data-testid={`tax-year-${ty.id}`}>
                  {ty.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Daily shortcuts and recently touched records */}
      <div className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
        <Card className="border-stone-100 bg-white card-shadow" data-testid="quick-actions-card">
          <CardHeader><CardTitle className="text-lg font-medium text-stone-800">Quick actions</CardTitle><p className="text-xs text-stone-500">Start the jobs you use most often.</p></CardHeader>
          <CardContent className="grid grid-cols-2 gap-3">
            {[
              { label: "New invoice", path: "/invoices?action=new", icon: FileText },
              { label: "New expense", path: "/expenses?action=new", icon: Receipt },
              { label: "Plan outgoing", path: "/cash-flow?action=new", icon: CalendarClock },
              { label: "Import statement", path: "/bank-statements", icon: Building2 },
            ].map((action) => <button key={action.label} onClick={() => navigate(action.path)} className="flex items-center gap-3 rounded-lg border border-stone-200 p-3 text-left text-sm font-semibold text-stone-700 transition hover:border-[#C7A76D] hover:bg-[#C7A76D]/5"><span className="flex h-9 w-9 items-center justify-center rounded-md bg-[#C7A76D]/10 text-[#9A7B43]"><action.icon className="h-4 w-4" /></span>{action.label}</button>)}
            <button onClick={() => navigate("/cash-flow")} className="col-span-2 flex items-center justify-between rounded-lg bg-stone-900 p-4 text-left text-white">
              <span><span className="block text-xs text-stone-300">Next 30 days</span><span className="mt-0.5 block font-mono text-xl font-semibold">{formatCurrency(cashPreview?.totals?.net)}</span><span className="text-xs text-stone-300">expected net movement</span></span><ChevronRight className="h-5 w-5" />
            </button>
          </CardContent>
        </Card>

        <Card className="border-stone-100 bg-white card-shadow" data-testid="recent-records-card">
          <CardHeader><CardTitle className="flex items-center gap-2 text-lg font-medium text-stone-800"><Clock3 className="h-5 w-5 text-[#C7A76D]" />Recent records</CardTitle><p className="text-xs text-stone-500">Jump straight back into something you recently changed.</p></CardHeader>
          <CardContent>
            {recent.length === 0 ? <p className="py-8 text-center text-sm text-stone-500">No recent records yet.</p> : <div className="divide-y divide-stone-100">{recent.map((item) => <button key={`${item.type}-${item.id}`} onClick={() => navigate(item.path)} className="flex w-full items-center gap-3 py-3 text-left hover:bg-stone-50"><span className="rounded bg-stone-100 px-2 py-1 text-[10px] font-bold uppercase text-stone-500">{item.type}</span><span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold text-stone-800">{item.title}</span><span className="block truncate text-xs text-stone-500">{item.subtitle}</span></span><span className="font-mono text-sm text-stone-600">{formatCurrency(item.amount)}</span><ChevronRight className="h-4 w-4 text-stone-300" /></button>)}</div>}
          </CardContent>
        </Card>
      </div>

      {/* Summary Cards - Bento Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {/* Total Income */}
        <Card className="bg-white border-stone-100 card-shadow hover:card-shadow-hover transition-all duration-300" data-testid="income-card">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-stone-500">Total Income</CardTitle>
            <div className="w-8 h-8 rounded-sm bg-emerald-50 flex items-center justify-center">
              <TrendingUp className="w-4 h-4 text-emerald-600" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-mono font-medium text-emerald-700" data-testid="total-income">
              {loading ? "..." : formatCurrency(summary?.total_income)}
            </div>
            <p className="text-xs text-stone-400 mt-1">
              {summary?.invoice_count || 0} invoices
            </p>
          </CardContent>
        </Card>

        {/* Total Expenses */}
        <Card className="bg-white border-stone-100 card-shadow hover:card-shadow-hover transition-all duration-300" data-testid="expenses-card">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-stone-500">Total Expenses</CardTitle>
            <div className="w-8 h-8 rounded-sm bg-rose-50 flex items-center justify-center">
              <TrendingDown className="w-4 h-4 text-rose-600" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-mono font-medium text-rose-700" data-testid="total-expenses">
              {loading ? "..." : formatCurrency(summary?.total_expenses)}
            </div>
            <p className="text-xs text-stone-400 mt-1">
              {summary?.expense_count || 0} expenses
            </p>
          </CardContent>
        </Card>

        {/* Net Profit */}
        <Card className="bg-white border-stone-100 card-shadow hover:card-shadow-hover transition-all duration-300" data-testid="profit-card">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-stone-500">Net Profit</CardTitle>
            <div className="w-8 h-8 rounded-sm bg-stone-100 flex items-center justify-center">
              <Wallet className="w-4 h-4 text-stone-600" />
            </div>
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-mono font-medium ${(summary?.net_profit || 0) >= 0 ? 'text-emerald-700' : 'text-rose-700'}`} data-testid="net-profit">
              {loading ? "..." : formatCurrency(summary?.net_profit)}
            </div>
            <p className="text-xs text-stone-400 mt-1">
              Income - Expenses
            </p>
          </CardContent>
        </Card>

        {/* Transactions */}
        <Card className="bg-white border-stone-100 card-shadow hover:card-shadow-hover transition-all duration-300" data-testid="transactions-card">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-stone-500">Bank Transactions</CardTitle>
            <div className="w-8 h-8 rounded-sm bg-stone-100 flex items-center justify-center">
              <ArrowLeftRight className="w-4 h-4 text-stone-600" />
            </div>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-mono font-medium text-stone-700" data-testid="transaction-count">
              {loading ? "..." : summary?.transaction_count || 0}
            </div>
            <p className="text-xs text-stone-400 mt-1">
              From bank statements
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Secondary Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Excluded Transactions */}
        <Card className="bg-white border-stone-100 card-shadow" data-testid="excluded-card">
          <CardHeader>
            <CardTitle className="text-base font-medium text-stone-700">Excluded from Totals</CardTitle>
            <p className="text-xs text-stone-400">HMRC, Mark Powell, Mark Adam Powell</p>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-sm text-stone-500">Owner Withdrawals</span>
              <span className="font-mono text-sm text-stone-600" data-testid="owner-withdrawals">
                {formatCurrency(summary?.owner_withdrawals)}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-stone-500">Tax Payments (HMRC)</span>
              <span className="font-mono text-sm text-stone-600" data-testid="tax-payments">
                {formatCurrency(summary?.tax_payments)}
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Income Breakdown */}
        <Card className="bg-white border-stone-100 card-shadow" data-testid="income-breakdown-card">
          <CardHeader>
            <CardTitle className="text-base font-medium text-stone-700">Income Breakdown</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-sm text-stone-500 flex items-center gap-2">
                <FileText className="w-3 h-3" /> Manual Invoices
              </span>
              <span className="font-mono text-sm text-emerald-600" data-testid="manual-income">
                {formatCurrency(summary?.manual_income)}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-stone-500 flex items-center gap-2">
                <ArrowLeftRight className="w-3 h-3" /> Bank Credits
              </span>
              <span className="font-mono text-sm text-emerald-600" data-testid="bank-income">
                {formatCurrency(summary?.bank_income)}
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Expense Breakdown */}
        <Card className="bg-white border-stone-100 card-shadow" data-testid="expense-breakdown-card">
          <CardHeader>
            <CardTitle className="text-base font-medium text-stone-700">Expense Breakdown</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-sm text-stone-500 flex items-center gap-2">
                <Receipt className="w-3 h-3" /> Manual Expenses
              </span>
              <span className="font-mono text-sm text-rose-600" data-testid="manual-expenses">
                {formatCurrency(summary?.manual_expenses)}
              </span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm text-stone-500 flex items-center gap-2">
                <ArrowLeftRight className="w-3 h-3" /> Bank Debits
              </span>
              <span className="font-mono text-sm text-rose-600" data-testid="bank-expenses">
                {formatCurrency(summary?.bank_expenses)}
              </span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Overdue Payment Alerts */}
      <OverdueAlerts overdue={extras?.overdue} />

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <MonthlyChart monthly={extras?.monthly} />
        <CategoryChart categories={extras?.categories} />
      </div>

      {/* Annual Comparison */}
      <ComparisonCard comparison={comparison} summary={summary} />

      {/* Data Management Section */}
      <Card className="bg-white border-stone-100 card-shadow" data-testid="data-management-card">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-sm bg-[#C7A76D] flex items-center justify-center">
              <HardDrive className="w-5 h-5 text-white" />
            </div>
            <div>
              <CardTitle className="text-lg font-medium text-stone-800">Data Management</CardTitle>
              <p className="text-xs text-stone-400">Downloads zip to your computer</p>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-4">
            <Button
              onClick={handleBackup}
              disabled={backupLoading}
              className="bg-[#C7A76D] text-white hover:bg-[#B8985E] rounded-sm px-6"
              data-testid="backup-btn"
            >
              {backupLoading ? (
                <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Download className="w-4 h-4 mr-2" />
              )}
              Backup All Data
            </Button>
            
            <label>
              <Button
                asChild
                variant="outline"
                disabled={restoreLoading}
                className="border-[#C7A76D] text-[#C7A76D] hover:bg-[#C7A76D]/10 rounded-sm px-6 cursor-pointer"
                data-testid="restore-btn"
              >
                <span>
                  {restoreLoading ? (
                    <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <Upload className="w-4 h-4 mr-2" />
                  )}
                  Restore from Backup
                </span>
              </Button>
              <input
                type="file"
                accept=".zip"
                onChange={handleRestore}
                className="hidden"
                data-testid="restore-input"
              />
            </label>
          </div>
          <p className="text-xs text-stone-400 mt-4">
            Backup includes all invoices, expenses, transactions, bank statements, and uploaded files.
          </p>
        </CardContent>
      </Card>
    </div>
  );
};

export default Dashboard;
