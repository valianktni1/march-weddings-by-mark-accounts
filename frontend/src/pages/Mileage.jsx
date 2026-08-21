import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Plus, Trash2, Car, Search } from "lucide-react";
import { formatCurrency, getCurrentTaxYear } from "@/utils/formatters";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const TAX_YEARS = [
  { id: "2023-24", label: "2023/24" }, { id: "2024-25", label: "2024/25" },
  { id: "2025-26", label: "2025/26" }, { id: "2026-27", label: "2026/27" },
  { id: "2027-28", label: "2027/28" }, { id: "2028-29", label: "2028/29" },
];

const Mileage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [taxYear, setTaxYear] = useState(searchParams.get("taxYear") || getCurrentTaxYear());
  const [searchQuery, setSearchQuery] = useState(searchParams.get("search") || "");
  const [data, setData] = useState({ entries: [], total_miles: 0, total_amount: 0 });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ date: "", description: "", from_location: "", to_location: "", miles: "", round_trip: false });

  const fetchMileage = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/mileage?tax_year=${taxYear}`);
      setData(res.data);
    } catch { toast.error("Failed to load mileage"); }
  }, [taxYear]);

  useEffect(() => { fetchMileage(); }, [fetchMileage]);

  useEffect(() => {
    if (searchParams.get("action") === "new") setOpen(true);
  }, [searchParams]);

  useEffect(() => {
    const requestedYear = searchParams.get("taxYear") || getCurrentTaxYear();
    const requestedSearch = searchParams.get("search") || "";
    if (requestedYear !== taxYear) setTaxYear(requestedYear);
    if (requestedSearch !== searchQuery) setSearchQuery(requestedSearch);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  useEffect(() => {
    const next = new URLSearchParams(searchParams);
    next.set("taxYear", taxYear);
    searchQuery ? next.set("search", searchQuery) : next.delete("search");
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taxYear, searchQuery]);

  const visibleEntries = data.entries.filter((entry) => {
    const needle = searchQuery.trim().toLowerCase();
    if (!needle) return true;
    return [entry.description, entry.from_location, entry.to_location].some((value) => String(value || "").toLowerCase().includes(needle));
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      await axios.post(`${API}/mileage`, { ...form, miles: parseFloat(form.miles), tax_year: taxYear });
      toast.success(form.round_trip ? "Round-trip mileage added" : "Mileage entry added");
      setForm({ date: "", description: "", from_location: "", to_location: "", miles: "", round_trip: false });
      setOpen(false);
      fetchMileage();
    } catch { toast.error("Failed to add mileage"); }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this mileage entry?")) return;
    try {
      await axios.delete(`${API}/mileage/${id}`);
      toast.success("Deleted");
      fetchMileage();
    } catch { toast.error("Failed to delete"); }
  };

  return (
    <div className="space-y-6" data-testid="mileage-page">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold text-stone-900" style={{ fontFamily: 'Playfair Display, serif' }}>Mileage Log</h2>
          <p className="text-sm text-stone-500 mt-1">Track business mileage at HMRC approved rates</p>
        </div>
        <div className="flex items-center gap-3">
          <Select value={taxYear} onValueChange={setTaxYear} data-testid="mileage-tax-year">
            <SelectTrigger className="w-[130px] border-stone-200"><SelectValue /></SelectTrigger>
            <SelectContent>{TAX_YEARS.map(ty => <SelectItem key={ty.id} value={ty.id}>{ty.label}</SelectItem>)}</SelectContent>
          </Select>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button className="bg-[#C7A76D] text-white hover:bg-[#B8985E] rounded-sm" data-testid="add-mileage-btn">
                <Plus className="w-4 h-4 mr-2" /> Add Trip
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-md" data-testid="add-mileage-dialog">
              <DialogHeader><DialogTitle>Log Mileage</DialogTitle></DialogHeader>
              <form onSubmit={handleSubmit} className="space-y-3">
                <div className="space-y-2">
                  <Label>Date *</Label>
                  <Input type="date" value={form.date} onChange={e => setForm({...form, date: e.target.value})} required className="border-stone-200" data-testid="mileage-date" />
                </div>
                <div className="space-y-2">
                  <Label>Description *</Label>
                  <Input value={form.description} onChange={e => setForm({...form, description: e.target.value})} placeholder="e.g. Wedding shoot - Smith" required className="border-stone-200" data-testid="mileage-desc" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <Label>From</Label>
                    <Input value={form.from_location} onChange={e => setForm({...form, from_location: e.target.value})} placeholder="Home" className="border-stone-200" data-testid="mileage-from" />
                  </div>
                  <div className="space-y-2">
                    <Label>To</Label>
                    <Input value={form.to_location} onChange={e => setForm({...form, to_location: e.target.value})} placeholder="Venue" className="border-stone-200" data-testid="mileage-to" />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label>{form.round_trip ? "Miles (one way) *" : "Miles travelled *"}</Label>
                  <Input type="number" step="0.1" value={form.miles} onChange={e => setForm({...form, miles: e.target.value})} required className="border-stone-200 font-mono" data-testid="mileage-miles" />
                </div>
                <label className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition ${form.round_trip ? "border-[#C7A76D] bg-[#C7A76D]/10" : "border-stone-200 bg-white"}`}>
                  <Checkbox checked={form.round_trip} onCheckedChange={(checked) => setForm({ ...form, round_trip: checked === true })} data-testid="mileage-round-trip" />
                  <span><span className="block text-sm font-semibold text-stone-800">Round trip - double this mileage</span><span className="block text-xs text-stone-500">Use for a straightforward journey to the wedding and back with no other venues.</span></span>
                </label>
                <div className="bg-stone-50 rounded p-3 text-sm">
                  <p className="text-stone-500">HMRC Rate: <span className="font-mono">{taxYear >= "2026-27" ? "55p" : "45p"}/mile</span> (first 10,000) then <span className="font-mono">25p/mile</span></p>
                  {form.miles && <><p className="text-stone-700 mt-1">Mileage recorded: <span className="font-mono font-medium">{(parseFloat(form.miles || 0) * (form.round_trip ? 2 : 1)).toFixed(1)} miles</span>{form.round_trip && <span className="text-stone-500"> ({parseFloat(form.miles || 0).toFixed(1)} each way)</span>}</p><p className="text-stone-700 mt-1">Estimated claim: <span className="font-mono font-medium">{formatCurrency(parseFloat(form.miles || 0) * (form.round_trip ? 2 : 1) * (taxYear >= "2026-27" ? 0.55 : 0.45))}</span></p></>}
                </div>
                <Button type="submit" className="w-full bg-[#C7A76D] hover:bg-[#B8985E] text-white rounded-sm" data-testid="submit-mileage-btn">Add Mileage Entry</Button>
              </form>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="bg-white border-stone-100 card-shadow">
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-md bg-[#C7A76D]/10 flex items-center justify-center"><Car className="w-5 h-5 text-[#C7A76D]" /></div>
              <div>
                <p className="text-xs text-stone-500">Total Miles</p>
                <p className="text-xl font-semibold font-mono text-stone-900">{data.total_miles.toLocaleString()}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-white border-stone-100 card-shadow">
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-md bg-emerald-50 flex items-center justify-center"><Car className="w-5 h-5 text-emerald-600" /></div>
              <div>
                <p className="text-xs text-stone-500">Total Claimable</p>
                <p className="text-xl font-semibold font-mono text-emerald-700">{formatCurrency(data.total_amount)}</p>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-white border-stone-100 card-shadow">
          <CardContent className="pt-6">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-md bg-stone-100 flex items-center justify-center"><Car className="w-5 h-5 text-stone-500" /></div>
              <div>
                <p className="text-xs text-stone-500">Miles Remaining at {taxYear >= "2026-27" ? "55p" : "45p"}</p>
                <p className="text-xl font-semibold font-mono text-stone-700">{Math.max(0, 10000 - data.total_miles).toLocaleString()}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Table */}
      <Card className="bg-white border-stone-100 card-shadow">
        <CardContent className="pt-6">
          <div className="relative mb-4 max-w-sm"><Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" /><Input value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="Search mileage…" className="pl-9" /></div>
          {visibleEntries.length === 0 ? (
            <div className="text-center py-12 text-stone-400">
              <Car className="w-10 h-10 mx-auto mb-3 opacity-40" />
              <p>No mileage entries for this tax year</p>
              <p className="text-xs mt-1">Click "Add Trip" to start logging your business mileage</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead>Route</TableHead>
                  <TableHead className="text-right">Miles</TableHead>
                  <TableHead className="text-right">Rate</TableHead>
                  <TableHead className="text-right">Claim</TableHead>
                  <TableHead className="w-10"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {[...visibleEntries].sort((a, b) => {
                  const da = a.date.split("/").reverse().join("");
                  const db = b.date.split("/").reverse().join("");
                  return db.localeCompare(da);
                }).map(entry => (
                  <TableRow key={entry.id} data-testid={"mileage-row-" + entry.id} className={searchParams.get("focus") === entry.id ? "bg-[#C7A76D]/10" : ""}>
                    <TableCell className="font-mono text-sm">{entry.date}</TableCell>
                    <TableCell className="text-sm">{entry.description}</TableCell>
                    <TableCell className="text-sm text-stone-500">{entry.from_location} → {entry.to_location}{entry.round_trip && <span className="mt-1 block w-fit rounded bg-[#C7A76D]/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-[#80642F]">Round trip</span>}</TableCell>
                    <TableCell className="text-right font-mono text-sm">{entry.miles}{entry.round_trip && entry.one_way_miles != null && <span className="block font-sans text-[10px] text-stone-400">{entry.one_way_miles} each way</span>}</TableCell>
                    <TableCell className="text-right font-mono text-sm">{Math.round((entry.rate || 0) * 100)}p</TableCell>
                    <TableCell className="text-right font-mono text-sm font-medium">{formatCurrency(entry.amount)}</TableCell>
                    <TableCell>
                      <Button variant="ghost" size="icon" className="h-7 w-7 text-stone-400 hover:text-rose-500" onClick={() => handleDelete(entry.id)} data-testid={"delete-mileage-" + entry.id}>
                        <Trash2 className="w-3 h-3" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default Mileage;
