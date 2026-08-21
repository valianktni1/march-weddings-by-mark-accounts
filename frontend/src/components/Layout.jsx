import { Outlet, NavLink } from "react-router-dom";
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
];

export const Layout = ({ user, onSignOut }) => {
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
        <div className="p-4 sm:p-6 md:p-8 max-w-7xl mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
};

export default Layout;
