using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Centesimo.Desktop.Models;

namespace Centesimo.Desktop.ViewModels;

/// <summary>
/// Home a widget (§2.11).
///
/// Layout a griglia fissa e configurabile (range temporale + conti), non drag&amp;drop:
/// scelta esplicita dell'MVP, il riposizionamento libero è un'iterazione successiva.
/// Tutti i widget si appoggiano a endpoint già esistenti — nessuna API dedicata.
/// </summary>
public partial class DashboardViewModel : PageViewModel
{
    public override string Title => "Home";
    public override string Glyph => "◧";

    public ObservableCollection<Account> Accounts { get; } = [];
    public ObservableCollection<Budget> Budgets { get; } = [];
    public ObservableCollection<Transaction> Upcoming { get; } = [];
    public ObservableCollection<TimeseriesPoint> BalanceSeries { get; } = [];
    public ObservableCollection<TimeseriesPoint> NetWorthSeries { get; } = [];

    public string[] Ranges { get; } = ["day", "week", "month", "year"];

    [ObservableProperty]
    private string _selectedRange = "month";

    [ObservableProperty]
    private NetWorth? _netWorth;

    [ObservableProperty]
    private decimal _totalAssets;

    [ObservableProperty]
    private decimal _monthSpending;

    [ObservableProperty]
    private decimal _monthIncome;

    partial void OnSelectedRangeChanged(string value) => _ = LoadAsync();

    public override Task LoadAsync() => RunAsync(LoadDataAsync);

    // Separata da LoadAsync perché i comandi la richiamano *dentro* la loro RunAsync:
    // annidare due RunAsync farebbe scattare la guardia su IsBusy e il refresh salterebbe.
    private async Task LoadDataAsync()
    {
        var accounts = await Api.GetAccountsAsync();
        Accounts.Clear();
        foreach (var account in accounts.Where(a => !a.IsLiability))
        {
            Accounts.Add(account);
        }
        TotalAssets = accounts.Where(a => !a.IsLiability).Sum(a => a.Balance);

        NetWorth = await Api.GetNetWorthAsync();

        var budgets = await Api.GetBudgetsAsync();
        Budgets.Clear();
        foreach (var budget in budgets)
        {
            Budgets.Add(budget);
        }

        var upcoming = await Api.GetUpcomingAsync(30);
        Upcoming.Clear();
        foreach (var item in upcoming.Items.Take(8))
        {
            Upcoming.Add(item);
        }

        var balance = await Api.GetTimeseriesAsync("balance", SelectedRange);
        BalanceSeries.Clear();
        foreach (var point in balance.Points)
        {
            BalanceSeries.Add(point);
        }

        var netWorthSeries = await Api.GetTimeseriesAsync("net_worth", SelectedRange);
        NetWorthSeries.Clear();
        foreach (var point in netWorthSeries.Points)
        {
            NetWorthSeries.Add(point);
        }

        var spending = await Api.GetTimeseriesAsync("spending", "month");
        MonthSpending = spending.Points.Sum(p => p.Value);

        var income = await Api.GetTimeseriesAsync("income", "month");
        MonthIncome = income.Points.Sum(p => p.Value);
    }

    [RelayCommand]
    private Task ConfirmUpcoming(Transaction? transaction) => transaction is null
        ? Task.CompletedTask
        : RunAsync(async () =>
        {
            await Api.ConfirmOccurrenceAsync(transaction.Id, null);
            await LoadDataAsync();
        }, "Occorrenza confermata");
}
