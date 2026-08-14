import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { AlertTriangle } from "lucide-react";
import { formatCurrency } from "@/utils/formatters";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";

const PIE_COLORS = ["#C7A76D", "#8B7355", "#A0522D", "#6B8E6B", "#708090", "#B8860B", "#5F7D8E", "#9E7B6B", "#7B8F6B", "#8B6B8E"];

export const OverdueAlerts = ({ overdue }) => {
  if (!overdue || overdue.length === 0) return null;
  return (
    <Card className="bg-white border-rose-200 card-shadow" data-testid="overdue-card">
      <CardHeader>
        <CardTitle className="text-base font-medium text-rose-700 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> Overdue Payments ({overdue.length})
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {overdue.map((inv) => (
            <div key={inv.id} className="flex items-center justify-between py-2 px-3 bg-rose-50 rounded" data-testid={"overdue-" + inv.id}>
              <div>
                <span className="font-medium text-sm text-stone-800">{inv.couple_names}</span>
                <span className="text-xs text-stone-400 ml-2">{inv.invoice_number}</span>
              </div>
              <div className="text-right">
                <span className="font-mono text-sm text-rose-700">{formatCurrency(inv.balance)}</span>
                <span className="text-xs text-rose-500 ml-2">Due {inv.due_date} ({inv.days_overdue}d overdue)</span>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

export const MonthlyChart = ({ monthly }) => (
  <Card className="bg-white border-stone-100 card-shadow" data-testid="monthly-chart-card">
    <CardHeader>
      <CardTitle className="text-base font-medium text-stone-700">Monthly Profit & Loss</CardTitle>
    </CardHeader>
    <CardContent>
      {monthly ? (
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={monthly} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
            <XAxis dataKey="month" tick={{ fontSize: 12, fill: "#78716c" }} />
            <YAxis tick={{ fontSize: 11, fill: "#78716c" }} tickFormatter={(v) => "£" + v} />
            <Tooltip formatter={(value) => ["£" + value.toFixed(2), undefined]} contentStyle={{ borderRadius: 4, border: "1px solid #e7e5e4" }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="income" name="Income" fill="#6B8E6B" radius={[2, 2, 0, 0]} />
            <Bar dataKey="expenses" name="Expenses" fill="#C7A76D" radius={[2, 2, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <div className="h-[280px] flex items-center justify-center text-stone-400">Loading...</div>
      )}
    </CardContent>
  </Card>
);

export const CategoryChart = ({ categories }) => (
  <Card className="bg-white border-stone-100 card-shadow" data-testid="category-chart-card">
    <CardHeader>
      <CardTitle className="text-base font-medium text-stone-700">Expense Categories</CardTitle>
    </CardHeader>
    <CardContent>
      {categories && categories.length > 0 ? (
        <div className="flex items-center gap-4">
          <ResponsiveContainer width="50%" height={280}>
            <PieChart>
              <Pie data={categories} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={100} innerRadius={50}>
                {categories.map((entry, idx) => (
                  <Cell key={entry.name} fill={PIE_COLORS[idx % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(value) => ["£" + value.toFixed(2), undefined]} />
            </PieChart>
          </ResponsiveContainer>
          <div className="w-1/2 space-y-1">
            {categories.map((cat, idx) => (
              <div key={cat.name} className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-sm" style={{ backgroundColor: PIE_COLORS[idx % PIE_COLORS.length] }} />
                  <span className="text-stone-600 truncate max-w-[140px]">{cat.name}</span>
                </div>
                <span className="font-mono text-stone-700">{formatCurrency(cat.value)}</span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="h-[280px] flex items-center justify-center text-stone-400">No expense data</div>
      )}
    </CardContent>
  </Card>
);

export const ComparisonCard = ({ comparison, summary }) => {
  if (!comparison || !summary) return null;
  const rows = [
    { label: "Income", prev: comparison.total_income || 0, curr: summary.total_income || 0 },
    { label: "Expenses", prev: comparison.total_expenses || 0, curr: summary.total_expenses || 0 },
    { label: "Net Profit", prev: comparison.net_profit || 0, curr: summary.net_profit || 0 },
  ];
  return (
    <Card className="bg-white border-stone-100 card-shadow" data-testid="comparison-card">
      <CardHeader>
        <CardTitle className="text-base font-medium text-stone-700">Year-on-Year Comparison</CardTitle>
      </CardHeader>
      <CardContent>
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th className="text-left font-medium text-stone-500 pb-2"></th>
              <th className="text-right font-medium text-stone-500 pb-2">{comparison.tax_year}</th>
              <th className="text-right font-medium text-stone-500 pb-2">{summary.tax_year}</th>
              <th className="text-right font-medium text-stone-500 pb-2">Change</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const diff = row.curr - row.prev;
              const pct = row.prev > 0 ? ((diff / row.prev) * 100).toFixed(0) : null;
              return (
                <tr key={row.label} className="border-t border-stone-100">
                  <td className="text-stone-600 py-2">{row.label}</td>
                  <td className="font-mono text-right py-2 text-stone-500">{formatCurrency(row.prev)}</td>
                  <td className="font-mono text-right py-2 text-stone-800">{formatCurrency(row.curr)}</td>
                  <td className={"font-mono text-right py-2 " + (diff >= 0 ? "text-emerald-600" : "text-rose-600")}>
                    {diff >= 0 ? "+" : ""}{formatCurrency(diff)}{pct ? " (" + pct + "%)" : ""}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
};
