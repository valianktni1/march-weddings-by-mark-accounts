import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  AlertCircle, ArrowRight, CheckCircle2, History, ListChecks, RefreshCw, TriangleAlert,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const money = (value) => new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(Number(value || 0));

export default function TidyUp() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await axios.get(`${API}/tidy-up`);
      setData(response.data);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Could not load the tidy-up dashboard");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading || !data) {
    return <div className="flex min-h-[50vh] items-center justify-center text-stone-500"><RefreshCw className="mr-2 h-5 w-5 animate-spin" />Checking every tax year…</div>;
  }

  const totals = data.totals || {};

  return (
    <div className="space-y-6 animate-fade-in" data-testid="historical-tidy-up-page">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-2 text-sm font-semibold uppercase tracking-[0.16em] text-[#9a793e]"><History className="h-4 w-4" />Historical records</div>
          <h1 className="text-3xl font-medium tracking-tight text-stone-900" style={{ fontFamily: "Playfair Display, serif" }}>Accounts Tidy-up</h1>
          <p className="mt-1 max-w-2xl text-sm text-stone-500">See every year in one place, then open the exact records that still need a decision.</p>
        </div>
        <Button variant="outline" onClick={load}><RefreshCw className="mr-2 h-4 w-4" />Recheck all years</Button>
      </div>

      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <Card className="border-stone-200"><CardContent className="p-5"><p className="text-sm text-stone-500">Open years</p><p className="mt-2 text-3xl font-semibold text-stone-900">{totals.open_years || 0}</p></CardContent></Card>
        <Card className={totals.blockers ? "border-rose-200 bg-rose-50/60" : "border-emerald-200 bg-emerald-50/60"}><CardContent className="p-5"><p className="text-sm text-stone-500">Blocking checks</p><p className={`mt-2 text-3xl font-semibold ${totals.blockers ? "text-rose-700" : "text-emerald-700"}`}>{totals.blockers || 0}</p></CardContent></Card>
        <Card className="border-amber-200 bg-amber-50/60"><CardContent className="p-5"><p className="text-sm text-stone-500">Warnings</p><p className="mt-2 text-3xl font-semibold text-amber-700">{totals.warnings || 0}</p></CardContent></Card>
        <Card className="border-[#C7A76D]/40 bg-[#C7A76D]/5"><CardContent className="p-5"><p className="text-sm text-stone-500">Records needing review</p><p className="mt-2 text-3xl font-semibold text-[#8a682d]">{totals.affected_records || 0}</p></CardContent></Card>
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        {(data.years || []).map((year) => {
          const clear = year.blocker_count === 0 && year.warning_count === 0;
          const closed = year.status === "closed";
          return <Card key={year.tax_year} className={`overflow-hidden border-stone-200 ${year.tax_year === data.current_tax_year ? "ring-1 ring-[#C7A76D]/60" : ""}`} data-testid={`tidy-year-${year.tax_year}`}>
            <CardHeader className="border-b border-stone-100 bg-stone-50/60 pb-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div><CardTitle className="text-xl">Tax year {year.label}</CardTitle><p className="mt-1 text-xs text-stone-500">{year.activity_count} expense, bank and mileage records</p></div>
                <div className="flex flex-wrap gap-2">
                  {year.tax_year === data.current_tax_year && <Badge className="bg-[#C7A76D]/15 text-[#806027]">Current year</Badge>}
                  <Badge className={closed ? "bg-emerald-100 text-emerald-800" : "bg-sky-100 text-sky-800"}>{closed ? "Closed" : "Open"}</Badge>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4 p-5">
              {clear ? <div className="flex items-center gap-3 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-emerald-900"><CheckCircle2 className="h-5 w-5 shrink-0" /><div><p className="font-semibold">No tidy-up items</p><p className="text-sm text-emerald-700">All automated checks are currently clear.</p></div></div>
                : <>
                  <div className="flex gap-3">
                    <div className="flex flex-1 items-center gap-2 rounded-lg bg-rose-50 p-3"><AlertCircle className="h-4 w-4 text-rose-600" /><span className="text-sm"><strong>{year.blocker_count}</strong> blocking</span></div>
                    <div className="flex flex-1 items-center gap-2 rounded-lg bg-amber-50 p-3"><TriangleAlert className="h-4 w-4 text-amber-600" /><span className="text-sm"><strong>{year.warning_count}</strong> warnings</span></div>
                  </div>
                  <div className="space-y-2">
                    {year.checks.map((check) => <div key={check.code} className="flex items-center justify-between gap-3 rounded-lg border border-stone-100 p-3 text-sm"><div className="min-w-0"><p className="truncate font-medium text-stone-800">{check.title}</p><p className="text-xs text-stone-500">{check.count} record{check.count === 1 ? "" : "s"}{check.amount ? ` · ${money(check.amount)}` : ""}</p></div><Badge className={check.severity === "blocker" ? "bg-rose-100 text-rose-800" : "bg-amber-100 text-amber-800"}>{check.severity}</Badge></div>)}
                  </div>
                </>}
              <Button className="w-full bg-[#1f2933] text-white hover:bg-[#111827]" onClick={() => navigate(`/tax-prep?year=${year.tax_year}`)}>
                <ListChecks className="mr-2 h-4 w-4" />{clear ? "Open tax-year review" : "Open Action Centre"}<ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </CardContent>
          </Card>;
        })}
      </div>
    </div>
  );
}
