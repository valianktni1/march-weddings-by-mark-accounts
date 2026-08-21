import { useEffect, useState } from "react";
import { Outlet, NavLink, useNavigate } from "react-router-dom";
import axios from "axios";
import { 
  LayoutDashboard, 
  FileText, 
  Receipt, 
  Building2, 
  ArrowLeftRight,
  Camera,
  Calculator,
  ListChecks,
  Car,
  CalendarClock,
  ArrowLeft,
  ArrowRight,
  Search,
  LogOut
} from "lucide-react";

const navItems = [
  { path: "/", label: "Dashboard", icon: LayoutDashboard },
  { path: "/invoices", label: "Invoices", icon: FileText },
  { path: "/expenses", label: "Expenses", icon: Receipt },
  { path: "/mileage", label: "Mileage", icon: Car },
  { path: "/bank-statements", label: "Bank Statements", icon: Building2 },
  { path: "/transactions", label: "Transactions", icon: ArrowLeftRight },
  { path: "/tax-prep", label: "Tax Year Close", icon: Calculator },
  { path: "/tidy-up", label: "Tidy Up", icon: ListChecks },
  { path: "/cash-flow", label: "Cash Flow", icon: CalendarClock },
];

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export const Layout = ({ user, onSignOut }) => {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    if (search.trim().length < 2) { setResults([]); setSearching(false); return undefined; }
    setSearching(true);
    const timer = window.setTimeout(async () => {
      try {
        const response = await axios.get(`${API}/search`, { params: { q: search.trim(), limit: 10 } });
        setResults(response.data);
      } catch { setResults([]); }
      finally { setSearching(false); }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [search]);

  const openResult = (path) => {
    navigate(path);
    setSearch("");
    setResults([]);
  };

  return (
    <div className="min-h-screen bg-[#FAFAF9]" data-testid="app-layout">
      {/* Sidebar */}
      <aside className="md:fixed left-0 top-0 md:h-full w-full md:w-64 bg-white border-b md:border-b-0 md:border-r border-stone-200 p-4 md:p-6 z-10" data-testid="sidebar">
        {/* Logo / Brand */}
        <div className="flex items-center gap-3 mb-4 md:mb-10">
          <div className="w-10 h-10 rounded-md bg-[#C7A76D] flex items-center justify-center">
            <Camera className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-stone-900" style={{ fontFamily: 'Playfair Display, serif' }}>
              Weddings by Mark
            </h1>
            <p className="text-xs text-stone-500">Financial Manager</p>
          </div>
          <button onClick={onSignOut} className="ml-auto md:hidden inline-flex items-center gap-2 rounded-lg border border-stone-200 px-3 py-2 text-xs font-semibold text-stone-600">
            <LogOut className="h-4 w-4" /> Sign out
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex md:block gap-2 md:space-y-1 overflow-x-auto pb-1 md:pb-0">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === "/"}
              data-testid={`nav-${item.label.toLowerCase().replace(/\s/g, '-')}`}
              className={({ isActive }) =>
                `flex shrink-0 items-center gap-2 md:gap-3 px-3 md:px-4 py-2.5 md:py-3 rounded-md text-sm font-medium transition-all duration-200 ${
                  isActive
                    ? "bg-[#C7A76D] text-white"
                    : "text-stone-600 hover:bg-[#C7A76D]/10 hover:text-[#C7A76D]"
                }`
              }
            >
              <item.icon className="w-4 h-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        {/* Footer */}
        <div className="hidden md:block absolute bottom-6 left-6 right-6 space-y-3">
          <div className="rounded-lg bg-stone-50 px-3 py-2">
            <p className="truncate text-xs font-medium text-stone-700">{user?.email}</p>
            <button onClick={onSignOut} className="mt-2 flex items-center gap-2 text-xs font-semibold text-stone-500 hover:text-rose-700">
              <LogOut className="h-3.5 w-3.5" /> Sign out
            </button>
          </div>
          <div className="text-xs text-stone-400 text-center">
            <p>UK Tax Year Format</p>
            <p className="font-mono">GBP • DD/MM/YYYY</p>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="md:ml-64 min-h-screen">
        <div className="sticky top-0 z-20 border-b border-stone-200 bg-[#FAFAF9]/95 px-4 py-3 backdrop-blur sm:px-6 md:px-8">
          <div className="mx-auto flex max-w-7xl items-center gap-2">
            <ButtonIcon label="Go back" onClick={() => navigate(-1)}><ArrowLeft className="h-4 w-4" /></ButtonIcon>
            <ButtonIcon label="Go forward" onClick={() => navigate(1)}><ArrowRight className="h-4 w-4" /></ButtonIcon>
            <div className="relative ml-1 max-w-xl flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                onKeyDown={(event) => { if (event.key === "Enter" && results[0]) openResult(results[0].path); }}
                placeholder="Search invoices, expenses, bank records…"
                aria-label="Search all accounts"
                className="h-10 w-full rounded-lg border border-stone-200 bg-white pl-9 pr-3 text-sm outline-none transition focus:border-[#C7A76D] focus:ring-2 focus:ring-[#C7A76D]/20"
                data-testid="global-search"
              />
              {(search.trim().length >= 2) && (
                <div className="absolute left-0 right-0 top-12 z-40 overflow-hidden rounded-lg border border-stone-200 bg-white shadow-xl" data-testid="global-search-results">
                  {searching ? <p className="p-4 text-sm text-stone-500">Searching…</p> : results.length === 0 ? <p className="p-4 text-sm text-stone-500">No matching records</p> : results.map((item) => (
                    <button key={`${item.type}-${item.id}`} onClick={() => openResult(item.path)} className="flex w-full items-start gap-3 border-b border-stone-100 px-4 py-3 text-left last:border-0 hover:bg-stone-50">
                      <span className="mt-0.5 rounded bg-[#C7A76D]/10 px-2 py-0.5 text-[10px] font-bold uppercase text-[#8A6C37]">{item.type}</span>
                      <span className="min-w-0"><span className="block truncate text-sm font-semibold text-stone-800">{item.title}</span><span className="block truncate text-xs text-stone-500">{item.subtitle}</span></span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
        <div className="p-4 sm:p-6 md:p-8 max-w-7xl mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
};

const ButtonIcon = ({ label, onClick, children }) => (
  <button type="button" onClick={onClick} aria-label={label} title={label} className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-stone-200 bg-white text-stone-600 hover:border-[#C7A76D] hover:text-[#9A7B43]">
    {children}
  </button>
);

export default Layout;
