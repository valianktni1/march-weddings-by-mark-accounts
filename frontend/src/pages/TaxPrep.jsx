import React, { useState, useEffect } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { Download, TrendingUp, TrendingDown, PoundSterling, Calculator } from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

function fmt(val) {
  if (val === undefined || val === null) return "\u00A30.00";
  return "\u00A3" + Number(val).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function TaxPrep() {
  const [taxYears, setTaxYears] = useState([]);
  const [taxYear, setTaxYear] = useState("2025-26");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(function() {
    axios.get(API + "/tax-years").then(function(res) {
      setTaxYears(res.data);
    });
  }, []);

  useEffect(function() {
    setLoading(true);
    axios.get(API + "/tax-prep/" + taxYear)
      .then(function(res) { setData(res.data); })
      .catch(function() { toast.error("Failed to load tax data"); })
      .finally(function() { setLoading(false); });
  }, [taxYear]);

  function handleExport() {
    axios.get(API + "/tax-prep/" + taxYear + "/export", { responseType: "blob" })
      .then(function(res) {
        var url = window.URL.createObjectURL(new Blob([res.data]));
        var a = document.createElement("a");
        a.href = url;
        a.download = "weddings_by_mark_tax_" + taxYear + ".csv";
        a.click();
        window.URL.revokeObjectURL(url);
        toast.success("Tax report downloaded");
      })
      .catch(function() { toast.error("Failed to export"); });
  }

  function handleQuarterExport(quarterName) {
    axios.get(API + "/tax-prep/" + taxYear + "/export/" + quarterName, { responseType: "blob" })
      .then(function(res) {
        var url = window.URL.createObjectURL(new Blob([res.data]));
        var a = document.createElement("a");
        a.href = url;
        a.download = "weddings_by_mark_" + taxYear + "_" + quarterName + ".csv";
        a.click();
        window.URL.revokeObjectURL(url);
        toast.success(quarterName + " report downloaded");
      })
      .catch(function() { toast.error("Failed to export " + quarterName); });
  }

  function renderCategories(q) {
    var entries = Object.entries(q.category_breakdown || {});
    if (entries.length === 0) return React.createElement("p", {className: "text-xs text-stone-400"}, "No expenses");
    return React.createElement("div", {className: "space-y-1"},
      entries.sort(function(a, b) { return b[1] - a[1]; }).map(function(entry) {
        return React.createElement("div", {key: entry[0], className: "flex justify-between text-xs"},
          React.createElement("span", {className: "text-stone-600"}, entry[0]),
          React.createElement("span", {className: "font-mono text-stone-900"}, fmt(entry[1]))
        );
      })
    );
  }

  if (loading) {
    return React.createElement("div", {className: "space-y-6"},
      React.createElement("h1", {className: "text-2xl font-semibold text-stone-900"}, "Prepare Tax Return"),
      React.createElement("p", {className: "text-stone-500"}, "Loading...")
    );
  }

  return React.createElement("div", {className: "space-y-6", "data-testid": "tax-prep-page"},
    React.createElement("div", {className: "flex items-center justify-between"},
      React.createElement("div", null,
        React.createElement("h1", {className: "text-2xl font-semibold text-stone-900", "data-testid": "tax-prep-title"}, "Prepare Tax Return"),
        React.createElement("p", {className: "text-sm text-stone-500 mt-1"}, "HMRC Making Tax Digital - Quarterly & Annual Summary")
      ),
      React.createElement("div", {className: "flex items-center gap-3"},
        React.createElement(Select, {value: taxYear, onValueChange: setTaxYear},
          React.createElement(SelectTrigger, {className: "w-36 bg-white border-stone-200", "data-testid": "tax-year-select"},
            React.createElement(SelectValue, null)
          ),
          React.createElement(SelectContent, null,
            taxYears.map(function(ty) {
              return React.createElement(SelectItem, {key: ty.id, value: ty.id}, ty.label);
            })
          )
        ),
        React.createElement(Button, {onClick: handleExport, className: "bg-[#C7A76D] hover:bg-[#B8964F] text-white", "data-testid": "export-csv-btn"},
          React.createElement(Download, {className: "w-4 h-4 mr-2"}),
          "Export CSV"
        )
      )
    ),
    data ? React.createElement(React.Fragment, null,
      React.createElement("div", {className: "grid grid-cols-2 md:grid-cols-4 gap-4"},
        React.createElement(Card, {className: "border-stone-200"},
          React.createElement(CardContent, {className: "pt-4 pb-4"},
            React.createElement("div", {className: "flex items-center gap-2 text-xs text-stone-500 mb-1"},
              React.createElement(TrendingUp, {className: "w-3 h-3"}), " Total Income"),
            React.createElement("p", {className: "text-lg font-semibold text-stone-900", "data-testid": "annual-income"}, fmt(data.annual.income))
          )
        ),
        React.createElement(Card, {className: "border-stone-200"},
          React.createElement(CardContent, {className: "pt-4 pb-4"},
            React.createElement("div", {className: "flex items-center gap-2 text-xs text-stone-500 mb-1"},
              React.createElement(TrendingDown, {className: "w-3 h-3"}), " Total Expenses"),
            React.createElement("p", {className: "text-lg font-semibold text-stone-900", "data-testid": "annual-expenses"}, fmt(data.annual.expenses))
          )
        ),
        React.createElement(Card, {className: "border-stone-200"},
          React.createElement(CardContent, {className: "pt-4 pb-4"},
            React.createElement("div", {className: "flex items-center gap-2 text-xs text-stone-500 mb-1"},
              React.createElement(PoundSterling, {className: "w-3 h-3"}), " Net Profit"),
            React.createElement("p", {className: "text-lg font-semibold text-emerald-700", "data-testid": "annual-profit"}, fmt(data.annual.profit))
          )
        ),
        React.createElement(Card, {className: "border-[#C7A76D]/30 bg-[#C7A76D]/5"},
          React.createElement(CardContent, {className: "pt-4 pb-4"},
            React.createElement("div", {className: "flex items-center gap-2 text-xs text-[#C7A76D] mb-1"},
              React.createElement(Calculator, {className: "w-3 h-3"}), " Est. Tax Due (20%)"),
            React.createElement("p", {className: "text-lg font-semibold text-[#C7A76D]", "data-testid": "annual-tax-estimate"}, fmt(data.annual.tax_due_estimate))
          )
        )
      ),
      React.createElement(Card, {className: "border-stone-200"},
        React.createElement(CardHeader, {className: "pb-3"},
          React.createElement(CardTitle, {className: "text-base text-stone-900"}, "Quarterly Breakdown")
        ),
        React.createElement(CardContent, null,
          React.createElement(Table, null,
            React.createElement(TableHeader, null,
              React.createElement(TableRow, {className: "border-stone-100"},
                React.createElement(TableHead, {className: "text-stone-500"}, "Quarter"),
                React.createElement(TableHead, {className: "text-stone-500"}, "Period"),
                React.createElement(TableHead, {className: "text-right text-stone-500"}, "Income"),
                React.createElement(TableHead, {className: "text-right text-stone-500"}, "Expenses"),
                React.createElement(TableHead, {className: "text-right text-stone-500"}, "Profit"),
                React.createElement(TableHead, {className: "text-right text-stone-500"}, "Txns"),
                React.createElement(TableHead, {className: "text-right text-stone-500"}, "Export")
              )
            ),
            React.createElement(TableBody, null,
              data.quarters.map(function(q) {
                return React.createElement(TableRow, {key: q.name, className: "border-stone-50", "data-testid": "quarter-" + q.name},
                  React.createElement(TableCell, {className: "font-medium text-stone-900"}, q.name),
                  React.createElement(TableCell, {className: "text-sm text-stone-600"}, q.label),
                  React.createElement(TableCell, {className: "text-right font-mono text-sm"}, fmt(q.income)),
                  React.createElement(TableCell, {className: "text-right font-mono text-sm"}, fmt(q.expenses)),
                  React.createElement(TableCell, {className: "text-right font-mono text-sm text-emerald-700"}, fmt(q.profit)),
                  React.createElement(TableCell, {className: "text-right text-sm text-stone-500"}, q.transaction_count),
                  React.createElement(TableCell, {className: "text-right"},
                    React.createElement(Button, {
                      variant: "ghost",
                      size: "sm",
                      onClick: function() { handleQuarterExport(q.name); },
                      className: "text-[#C7A76D] hover:text-[#B8964F] hover:bg-[#C7A76D]/10 h-7 px-2",
                      "data-testid": "export-" + q.name + "-btn"
                    },
                      React.createElement(Download, {className: "w-3 h-3 mr-1"}),
                      "CSV"
                    )
                  )
                );
              })
            )
          )
        )
      ),
      data.quarters.some(function(q) { return Object.keys(q.category_breakdown || {}).length > 0; }) ?
        React.createElement(Card, {className: "border-stone-200"},
          React.createElement(CardHeader, {className: "pb-3"},
            React.createElement(CardTitle, {className: "text-base text-stone-900"}, "Expense Breakdown by Category")
          ),
          React.createElement(CardContent, null,
            React.createElement("div", {className: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4"},
              data.quarters.map(function(q) {
                return React.createElement("div", {key: q.name},
                  React.createElement("h4", {className: "text-sm font-medium text-stone-700 mb-2"}, q.name + " - " + q.label.split(" - ")[0]),
                  renderCategories(q)
                );
              })
            )
          )
        ) : null
    ) : null
  );
}

export default TaxPrep;
