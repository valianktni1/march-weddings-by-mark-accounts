import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ArrowLeftRight, TrendingUp, TrendingDown, Ban, Building2, Search, ArrowUpDown, Receipt } from "lucide-react";
import { formatCurrency, formatDateUK, getCurrentTaxYear } from "@/utils/formatters";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const TAX_YEARS = [
  { id: "2023-24", label: "2023/24" },
  { id: "2024-25", label: "2024/25" },
  { id: "2025-26", label: "2025/26" },
  { id: "2026-27", label: "2026/27" },
  { id: "2027-28", label: "2027/28" },
  { id: "2028-29", label: "2028/29" },
  { id: "2029-30", label: "2029/30" },
];

const TRANSACTION_TYPES = {
  income: { label: "Income", icon: TrendingUp, color: "text-emerald-700", bg: "bg-emerald-50" },
  expense: { label: "Expense", icon: TrendingDown, color: "text-rose-700", bg: "bg-rose-50" },
  owner_withdrawal: { label: "Owner Withdrawal", icon: Ban, color: "text-stone-500", bg: "bg-stone-100" },
  tax_payment: { label: "HMRC Payment", icon: Building2, color: "text-amber-700", bg: "bg-amber-50" },
};

function parseUKDate(dateStr) {
  if (!dateStr) return new Date(0);
  var parts = dateStr.split("/");
  if (parts.length === 3) {
    return new Date(parts[2], parts[1] - 1, parts[0]);
  }
  return new Date(0);
}

export const Transactions = () => {
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterTaxYear, setFilterTaxYear] = useState("all");
  const [filterType, setFilterType] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [sortOrder, setSortOrder] = useState("newest");
  const [quickExpense, setQuickExpense] = useState(null);
  const [quickCategory, setQuickCategory] = useState("");
  const [quickSupplier, setQuickSupplier] = useState("");

  const EXPENSE_CATEGORIES = ["Equipment & Gear", "Software & Subscriptions", "Travel & Transport", "Insurance", "Marketing & Advertising", "Utilities", "Office Supplies", "Professional Services", "Meals", "Other"];

  const fetchTransactions = useCallback(async () => {
    setLoading(true);
    try {
      const params = filterTaxYear !== "all" ? { tax_year: filterTaxYear } : {};
      const response = await axios.get(`${API}/transactions`, { params });
      setTransactions(response.data);
    } catch (error) {
      console.error("Failed to fetch transactions:", error);
      toast.error("Failed to load transactions");
    } finally {
      setLoading(false);
    }
  }, [filterTaxYear]);

  useEffect(() => {
    fetchTransactions();
  }, [fetchTransactions]);

  const handleQuickExpense = async () => {
    if (!quickExpense || !quickCategory) return;
    try {
      await axios.post(`${API}/transactions/${quickExpense.id}/to-expense`, { category: quickCategory, supplier: quickSupplier });
      toast.success("Expense created & transaction categorised");
      setQuickExpense(null);
      setQuickCategory("");
      setQuickSupplier("");
      fetchTransactions();
    } catch { toast.error("Failed to create expense"); }
  };

  // Filter transactions by type and search query, then sort
  const filteredTransactions = transactions.filter(tx => {
    // Type filter
    if (filterType !== "all") {
      if (filterType === "excluded" && !tx.excluded_from_totals) return false;
      if (filterType === "uncategorised" && !(tx.transaction_type === "expense" && !tx.excluded_from_totals && !tx.category)) return false;
      if (filterType !== "excluded" && filterType !== "uncategorised" && tx.transaction_type !== filterType) return false;
    }
    // Search filter
    if (searchQuery.trim()) {
      return (tx.description || "").toLowerCase().includes(searchQuery.toLowerCase());
    }
    return true;
  }).sort((a, b) => {
    var dateA = parseUKDate(a.date);
    var dateB = parseUKDate(b.date);
    return sortOrder === "newest" ? dateB - dateA : dateA - dateB;
  });

  // Calculate summaries
  const summary = {
    income: transactions.filter(tx => tx.transaction_type === "income" && !tx.excluded_from_totals)
      .reduce((sum, tx) => sum + tx.amount, 0),
    expense: transactions.filter(tx => tx.transaction_type === "expense" && !tx.excluded_from_totals)
      .reduce((sum, tx) => sum + tx.amount, 0),
    excluded: transactions.filter(tx => tx.excluded_from_totals)
      .reduce((sum, tx) => sum + tx.amount, 0),
  };

  return (
    <div className="space-y-6 animate-fade-in" data-testid="transactions-page">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-medium tracking-tight text-stone-900" style={{ fontFamily: 'Playfair Display, serif' }}>
            Transactions
          </h1>
          <p className="text-stone-500 mt-1">All transactions from bank statements</p>
        </div>
        
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          {/* Search Bar */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-stone-400" />
            <Input
              type="text"
              placeholder="Search transactions..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 w-full sm:w-64 bg-white border-stone-200"
              data-testid="search-transactions"
            />
          </div>

          <Select value={filterType} onValueChange={setFilterType} data-testid="filter-type">
            <SelectTrigger className="w-full sm:w-44 bg-white border-stone-200">
              <SelectValue placeholder="Filter by type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Types</SelectItem>
              <SelectItem value="income">Income Only</SelectItem>
              <SelectItem value="expense">Expenses Only</SelectItem>
              <SelectItem value="uncategorised">Uncategorised Expenses</SelectItem>
              <SelectItem value="excluded">Excluded Only</SelectItem>
            </SelectContent>
          </Select>

          <Select value={sortOrder} onValueChange={setSortOrder} data-testid="sort-order">
            <SelectTrigger className="w-full sm:w-44 bg-white border-stone-200">
              <SelectValue placeholder="Sort by date" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="newest">Newest First</SelectItem>
              <SelectItem value="oldest">Oldest First</SelectItem>
            </SelectContent>
          </Select>

          <Select value={filterTaxYear} onValueChange={setFilterTaxYear} data-testid="filter-tax-year">
            <SelectTrigger className="w-full sm:w-36 bg-white border-stone-200">
              <SelectValue placeholder="Filter by year" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Years</SelectItem>
              {TAX_YEARS.map((ty) => (
                <SelectItem key={ty.id} value={ty.id}>
                  {ty.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card className="bg-white border-stone-100 card-shadow" data-testid="transactions-count-card">
          <CardContent className="py-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-sm bg-stone-100 flex items-center justify-center">
                <ArrowLeftRight className="w-5 h-5 text-stone-600" />
              </div>
              <div>
                <p className="text-sm text-stone-500">{filteredTransactions.length} Transactions</p>
                <p className="text-xs text-stone-400">From bank statements</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-white border-stone-100 card-shadow" data-testid="transactions-income-card">
          <CardContent className="py-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-sm bg-emerald-50 flex items-center justify-center">
                <TrendingUp className="w-5 h-5 text-emerald-600" />
              </div>
              <div>
                <p className="text-sm text-stone-500">Bank Income</p>
                <p className="font-mono text-lg font-medium text-emerald-700" data-testid="bank-income-total">
                  {formatCurrency(summary.income)}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-white border-stone-100 card-shadow" data-testid="transactions-expense-card">
          <CardContent className="py-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-sm bg-rose-50 flex items-center justify-center">
                <TrendingDown className="w-5 h-5 text-rose-600" />
              </div>
              <div>
                <p className="text-sm text-stone-500">Bank Expenses</p>
                <p className="font-mono text-lg font-medium text-rose-700" data-testid="bank-expense-total">
                  {formatCurrency(summary.expense)}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="bg-white border-stone-100 card-shadow" data-testid="transactions-excluded-card">
          <CardContent className="py-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-sm bg-stone-100 flex items-center justify-center">
                <Ban className="w-5 h-5 text-stone-500" />
              </div>
              <div>
                <p className="text-sm text-stone-500">Excluded</p>
                <p className="font-mono text-lg font-medium text-stone-600" data-testid="excluded-total">
                  {formatCurrency(summary.excluded)}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Transactions Table */}
      <Card className="bg-white border-stone-100 card-shadow" data-testid="transactions-table-card">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="border-stone-100">
                <TableHead className="text-stone-500">Date</TableHead>
                <TableHead className="text-stone-500">Description</TableHead>
                <TableHead className="text-stone-500">Type</TableHead>
                <TableHead className="text-stone-500">Tax Year</TableHead>
                <TableHead className="text-right text-stone-500">Amount</TableHead>
                <TableHead className="w-10"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-8 text-stone-400">
                    Loading...
                  </TableCell>
                </TableRow>
              ) : filteredTransactions.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-8 text-stone-400">
                    <div className="flex flex-col items-center gap-2">
                      <ArrowLeftRight className="w-8 h-8 text-stone-300" />
                      <p>No transactions found.</p>
                      <p className="text-xs">Upload and parse a bank statement to see transactions.</p>
                    </div>
                  </TableCell>
                </TableRow>
              ) : (
                filteredTransactions.map((tx) => {
                  const typeInfo = TRANSACTION_TYPES[tx.transaction_type] || TRANSACTION_TYPES.expense;
                  const TypeIcon = typeInfo.icon;
                  
                  return (
                    <TableRow 
                      key={tx.id} 
                      className={`border-stone-100 ${tx.excluded_from_totals ? 'opacity-60' : ''}`}
                      data-testid={`transaction-row-${tx.id}`}
                    >
                      <TableCell className="font-mono text-sm">{formatDateUK(tx.date)}</TableCell>
                      <TableCell className="font-medium max-w-md">
                        <div className="truncate">{tx.description}</div>
                        {tx.excluded_from_totals && (
                          <span className="text-xs text-stone-400">(excluded from totals)</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <span className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded-sm ${typeInfo.bg} ${typeInfo.color}`}>
                          <TypeIcon className="w-3 h-3" />
                          {typeInfo.label}
                        </span>
                      </TableCell>
                      <TableCell>
                        <span className="text-xs px-2 py-1 bg-stone-100 rounded-sm">
                          {TAX_YEARS.find(t => t.id === tx.tax_year)?.label || tx.tax_year}
                        </span>
                      </TableCell>
                      <TableCell className={`text-right font-mono font-medium ${typeInfo.color}`}>
                        {tx.transaction_type === "income" ? "+" : "-"}{formatCurrency(tx.amount)}
                      </TableCell>
                      <TableCell className="w-10">
                        {tx.transaction_type === "expense" && !tx.excluded_from_totals && !tx.category && (
                          <Button variant="ghost" size="icon" className="h-7 w-7 text-stone-400 hover:text-[#C7A76D]" title="Create as expense" onClick={() => { setQuickExpense(tx); setQuickCategory(""); setQuickSupplier(""); }} data-testid={"quick-expense-" + tx.id}>
                            <Receipt className="w-3.5 h-3.5" />
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Quick Expense Dialog */}
      <Dialog open={!!quickExpense} onOpenChange={(o) => { if (!o) setQuickExpense(null); }}>
        <DialogContent className="max-w-sm" data-testid="quick-expense-dialog">
          <DialogHeader><DialogTitle>Create Expense from Transaction</DialogTitle></DialogHeader>
          {quickExpense && (
            <div className="space-y-3">
              <div className="bg-stone-50 rounded p-3 text-sm">
                <p className="text-stone-700 font-medium">{quickExpense.description}</p>
                <p className="font-mono text-stone-500 mt-1">{formatCurrency(quickExpense.amount)} — {quickExpense.date}</p>
              </div>
              <div className="space-y-2">
                <Label>Category *</Label>
                <Select value={quickCategory} onValueChange={setQuickCategory}>
                  <SelectTrigger className="border-stone-200" data-testid="quick-category"><SelectValue placeholder="Select category" /></SelectTrigger>
                  <SelectContent>{EXPENSE_CATEGORIES.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Supplier</Label>
                <Input value={quickSupplier} onChange={e => setQuickSupplier(e.target.value)} placeholder="Optional" className="border-stone-200" data-testid="quick-supplier" />
              </div>
              <Button onClick={handleQuickExpense} disabled={!quickCategory} className="w-full bg-[#C7A76D] hover:bg-[#B8985E] text-white rounded-sm" data-testid="quick-expense-submit">
                Create Expense & Categorise
              </Button>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default Transactions;
