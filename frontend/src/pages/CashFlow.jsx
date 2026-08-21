import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { ArrowDownLeft, ArrowUpRight, CalendarClock, Pencil, Plus, Trash2, Wallet } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { formatCurrency } from "@/utils/formatters";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const EMPTY_COMMITMENT = { description: "", amount: "", next_due_date: "", recurrence: "none", category: "", active: true };

function ukToInput(value) {
  const parts = String(value || "").split("/");
  return parts.length === 3 ? `${parts[2]}-${parts[1]}-${parts[0]}` : value || "";
}

function inputToUK(value) {
  const parts = String(value || "").split("-");
  return parts.length === 3 ? `${parts[2]}/${parts[1]}/${parts[0]}` : value || "";
}

export default function CashFlow() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [forecast, setForecast] = useState(null);
  const [loading, setLoading] = useState(true);
  const [balanceOpen, setBalanceOpen] = useState(false);
  const [balance, setBalance] = useState("");
  const [commitmentOpen, setCommitmentOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_COMMITMENT);
  const [saving, setSaving] = useState(false);

  const fetchForecast = useCallback(async () => {
    setLoading(true);
    try {
      const response = await axios.get(`${API}/cash-flow?horizon_days=90`);
      setForecast(response.data);
      setBalance(response.data.starting_balance == null ? "" : String(response.data.starting_balance));
    } catch (error) {
      toast.error(error.response?.data?.detail || "Cash-flow forecast could not be loaded");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchForecast(); }, [fetchForecast]);

  useEffect(() => {
    if (searchParams.get("action") === "new") {
      setEditing(null);
      setForm(EMPTY_COMMITMENT);
      setCommitmentOpen(true);
    }
  }, [searchParams]);

  const closeCommitment = () => {
    setCommitmentOpen(false);
    setEditing(null);
    const next = new URLSearchParams(searchParams);
    next.delete("action");
    setSearchParams(next, { replace: true });
  };

  const openEdit = (item) => {
    setEditing(item);
    setForm({
      description: item.description || "",
      amount: String(item.amount || ""),
      next_due_date: ukToInput(item.next_due_date),
      recurrence: item.recurrence || "none",
      category: item.category || "",
      active: item.active !== false,
    });
    setCommitmentOpen(true);
  };

  const saveBalance = async () => {
    try {
      await axios.put(`${API}/cash-flow/balance`, { balance: balance === "" ? null : Number(balance) });
      toast.success(balance === "" ? "Starting balance removed" : "Starting balance updated");
      setBalanceOpen(false);
      fetchForecast();
    } catch (error) { toast.error(error.response?.data?.detail || "Balance could not be saved"); }
  };

  const saveCommitment = async (event) => {
    event.preventDefault();
    setSaving(true);
    const payload = { ...form, amount: Number(form.amount), next_due_date: inputToUK(form.next_due_date) };
    try {
      if (editing) await axios.put(`${API}/cash-flow/commitments/${editing.id}`, payload);
      else await axios.post(`${API}/cash-flow/commitments`, payload);
      toast.success(editing ? "Planned outgoing updated" : "Planned outgoing added");
      closeCommitment();
      fetchForecast();
    } catch (error) { toast.error(error.response?.data?.detail || "Planned outgoing could not be saved"); }
    finally { setSaving(false); }
  };

  const removeCommitment = async (item) => {
    if (!window.confirm(`Delete ${item.description}? This only removes it from the forecast.`)) return;
    try {
      await axios.delete(`${API}/cash-flow/commitments/${item.id}`);
      toast.success("Planned outgoing removed");
      fetchForecast();
    } catch (error) { toast.error(error.response?.data?.detail || "Planned outgoing could not be removed"); }
  };

  const timeline = useMemo(() => [
    ...(forecast?.incoming || []).map((row) => ({ ...row, direction: "in" })),
    ...(forecast?.outgoing || []).map((row) => ({ ...row, direction: "out" })),
  ].sort((a, b) => a.days_from_today - b.days_from_today), [forecast]);

  return (
    <div className="space-y-6 animate-fade-in" data-testid="cash-flow-page">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#9A7B43]">Planning only</p>
          <h1 className="text-3xl font-medium tracking-tight text-stone-900" style={{ fontFamily: "Playfair Display, serif" }}>Cash-flow forecast</h1>
          <p className="mt-1 text-sm text-stone-500">What is expected in and out over the next 30, 60 and 90 days.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => setBalanceOpen(true)}><Wallet className="mr-2 h-4 w-4" />Set bank balance</Button>
          <Button className="bg-[#C7A76D] text-white hover:bg-[#B8985E]" onClick={() => { setEditing(null); setForm(EMPTY_COMMITMENT); setCommitmentOpen(true); }}>
            <Plus className="mr-2 h-4 w-4" />Plan an outgoing
          </Button>
        </div>
      </div>

      <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
        This is a forecast, not part of your tax return. Incoming figures use unpaid invoice balances; planned outgoings never create expenses or bank transactions.
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {(forecast?.windows || [{ days: 30 }, { days: 60 }, { days: 90 }]).map((window) => (
          <Card key={window.days} className="border-stone-100 bg-white card-shadow" data-testid={`cash-window-${window.days}`}>
            <CardHeader className="pb-3"><CardTitle className="text-base text-stone-700">Next {window.days} days</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              <div className="flex justify-between text-sm"><span className="text-stone-500">Expected in</span><span className="font-mono text-emerald-700">{loading ? "…" : formatCurrency(window.incoming)}</span></div>
              <div className="flex justify-between text-sm"><span className="text-stone-500">Planned out</span><span className="font-mono text-rose-700">{loading ? "…" : formatCurrency(window.outgoing)}</span></div>
              <div className="flex justify-between border-t border-stone-100 pt-2 font-semibold"><span>Net movement</span><span className={`font-mono ${(window.net || 0) >= 0 ? "text-emerald-700" : "text-rose-700"}`}>{loading ? "…" : formatCurrency(window.net)}</span></div>
              {window.projected_balance != null && <div className="flex justify-between rounded bg-stone-50 px-2 py-1.5 text-sm"><span>Estimated balance</span><span className="font-mono font-semibold">{formatCurrency(window.projected_balance)}</span></div>}
            </CardContent>
          </Card>
        ))}
      </div>

      {!forecast?.starting_balance_configured && !loading && (
        <button onClick={() => setBalanceOpen(true)} className="w-full rounded-lg border border-dashed border-[#C7A76D] bg-[#C7A76D]/5 p-4 text-left text-sm text-stone-700">
          Add today’s bank balance if you want the forecast to show an estimated balance as well as money in and out.
        </button>
      )}

      {(forecast?.missing_due_dates || []).length > 0 && (
        <Card className="border-amber-200 bg-amber-50">
          <CardHeader><CardTitle className="text-base text-amber-900">{forecast.missing_due_dates.length} invoice balance{forecast.missing_due_dates.length === 1 ? " has" : "s have"} no payment due date</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm text-amber-900">
            <p>They are not guessed into the forecast. Add a final-payment due date to include them accurately.</p>
            {forecast.missing_due_dates.slice(0, 5).map((item) => <button key={item.id} onClick={() => navigate(item.path)} className="block font-semibold underline">{item.invoice_number || item.description} — {formatCurrency(item.amount)}</button>)}
          </CardContent>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-[1.35fr_1fr]">
        <Card className="border-stone-100 bg-white card-shadow">
          <CardHeader><CardTitle className="flex items-center gap-2 text-lg"><CalendarClock className="h-5 w-5 text-[#C7A76D]" />90-day timeline</CardTitle></CardHeader>
          <CardContent>
            {timeline.length === 0 ? <p className="py-8 text-center text-sm text-stone-500">Nothing is currently due within 90 days.</p> : (
              <div className="divide-y divide-stone-100">
                {timeline.map((item, index) => (
                  <button key={`${item.direction}-${item.id}-${item.due_date}-${index}`} onClick={() => item.path && navigate(item.path)} disabled={!item.path} className="flex w-full items-center gap-3 py-3 text-left disabled:cursor-default">
                    <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${item.direction === "in" ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}`}>
                      {item.direction === "in" ? <ArrowDownLeft className="h-4 w-4" /> : <ArrowUpRight className="h-4 w-4" />}
                    </span>
                    <span className="min-w-0 flex-1"><span className="block truncate font-medium text-stone-800">{item.description}</span><span className={`text-xs ${item.overdue ? "font-semibold text-rose-700" : "text-stone-500"}`}>{item.overdue ? "Overdue · " : ""}{item.due_date}</span></span>
                    <span className={`font-mono font-semibold ${item.direction === "in" ? "text-emerald-700" : "text-rose-700"}`}>{item.direction === "in" ? "+" : "−"}{formatCurrency(item.amount)}</span>
                  </button>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="border-stone-100 bg-white card-shadow">
          <CardHeader><CardTitle className="text-lg">Planned outgoings</CardTitle><p className="text-xs text-stone-500">Subscriptions, insurance and other expected payments.</p></CardHeader>
          <CardContent>
            {(forecast?.commitments || []).length === 0 ? <p className="py-6 text-center text-sm text-stone-500">No planned outgoings added yet.</p> : (
              <div className="space-y-2">
                {forecast.commitments.map((item) => (
                  <div key={item.id} className={`rounded-lg border p-3 ${searchParams.get("focus") === item.id ? "border-[#C7A76D] bg-[#C7A76D]/5" : "border-stone-100"}`}>
                    <div className="flex items-start gap-2"><div className="min-w-0 flex-1"><p className="truncate font-medium text-stone-800">{item.description}</p><p className="text-xs text-stone-500">{formatCurrency(item.amount)} · {item.recurrence === "none" ? "One-off" : item.recurrence} · next {item.next_due_date}</p></div>
                      <Button size="icon" variant="ghost" onClick={() => openEdit(item)} aria-label="Edit planned outgoing"><Pencil className="h-4 w-4" /></Button>
                      <Button size="icon" variant="ghost" onClick={() => removeCommitment(item)} aria-label="Delete planned outgoing"><Trash2 className="h-4 w-4 text-rose-600" /></Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Dialog open={balanceOpen} onOpenChange={setBalanceOpen}>
        <DialogContent className="max-w-sm"><DialogHeader><DialogTitle>Today’s bank balance</DialogTitle></DialogHeader>
          <div className="space-y-4"><p className="text-sm text-stone-500">Optional. This is only used to estimate future balances.</p><div className="space-y-2"><Label>Current balance (£)</Label><Input type="number" step="0.01" value={balance} onChange={(event) => setBalance(event.target.value)} placeholder="Leave blank to remove" /></div><Button onClick={saveBalance} className="w-full bg-[#C7A76D] text-white hover:bg-[#B8985E]">Save balance</Button></div>
        </DialogContent>
      </Dialog>

      <Dialog open={commitmentOpen} onOpenChange={(open) => open ? setCommitmentOpen(true) : closeCommitment()}>
        <DialogContent className="max-w-md"><DialogHeader><DialogTitle>{editing ? "Edit" : "Add"} planned outgoing</DialogTitle></DialogHeader>
          <form onSubmit={saveCommitment} className="space-y-4">
            <div className="space-y-2"><Label>Description *</Label><Input value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} placeholder="e.g. Public liability insurance" required /></div>
            <div className="grid grid-cols-2 gap-3"><div className="space-y-2"><Label>Amount (£) *</Label><Input type="number" min="0.01" step="0.01" value={form.amount} onChange={(event) => setForm({ ...form, amount: event.target.value })} required /></div><div className="space-y-2"><Label>Next payment *</Label><Input type="date" value={form.next_due_date} onChange={(event) => setForm({ ...form, next_due_date: event.target.value })} required /></div></div>
            <div className="grid grid-cols-2 gap-3"><div className="space-y-2"><Label>Repeats</Label><Select value={form.recurrence} onValueChange={(value) => setForm({ ...form, recurrence: value })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">One-off</SelectItem><SelectItem value="weekly">Weekly</SelectItem><SelectItem value="monthly">Monthly</SelectItem><SelectItem value="quarterly">Quarterly</SelectItem><SelectItem value="yearly">Yearly</SelectItem></SelectContent></Select></div><div className="space-y-2"><Label>Category</Label><Input value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })} placeholder="Optional" /></div></div>
            <Button disabled={saving} type="submit" className="w-full bg-[#C7A76D] text-white hover:bg-[#B8985E]">{saving ? "Saving…" : "Save planned outgoing"}</Button>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
