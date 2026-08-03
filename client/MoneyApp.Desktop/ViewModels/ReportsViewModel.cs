using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using MoneyApp.Desktop.Models;

namespace MoneyApp.Desktop.ViewModels;

/// <summary>
/// Report a tutto schermo (§2.11): stessa logica dei widget, area di disegno più grande.
/// Usa l'endpoint generico `/reports/timeseries`, quindi cambiare metrica o range non
/// richiede nessuna modifica al backend.
/// </summary>
public partial class ReportsViewModel : PageViewModel
{
    public override string Title => "Report";
    public override string Glyph => "◫";

    public ObservableCollection<TimeseriesPoint> Points { get; } = [];
    public ObservableCollection<CategoryBreakdownItem> Breakdown { get; } = [];

    public string[] Metrics { get; } = ["balance", "spending", "income", "net_worth"];
    public string[] Ranges { get; } = ["day", "week", "month", "year"];

    [ObservableProperty] private string _selectedMetric = "balance";
    [ObservableProperty] private string _selectedRange = "month";
    [ObservableProperty] private string _breakdownType = "expense";
    [ObservableProperty] private decimal _breakdownTotal;
    [ObservableProperty] private NetWorth? _netWorth;

    partial void OnSelectedMetricChanged(string value) => _ = LoadAsync();
    partial void OnSelectedRangeChanged(string value) => _ = LoadAsync();
    partial void OnBreakdownTypeChanged(string value) => _ = LoadAsync();

    public override Task LoadAsync() => RunAsync(async () =>
    {
        var series = await Api.GetTimeseriesAsync(SelectedMetric, SelectedRange);
        Points.Clear();
        foreach (var point in series.Points)
        {
            Points.Add(point);
        }

        var breakdown = await Api.GetBreakdownAsync(BreakdownType, SelectedRange);
        Breakdown.Clear();
        foreach (var item in breakdown.Items)
        {
            Breakdown.Add(item);
        }
        BreakdownTotal = breakdown.Total;

        NetWorth = await Api.GetNetWorthAsync();
    });
}
