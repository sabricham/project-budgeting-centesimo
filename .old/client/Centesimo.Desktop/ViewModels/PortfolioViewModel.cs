using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Centesimo.Desktop.Models;

namespace Centesimo.Desktop.ViewModels;

/// <summary>Riga della tabella posizioni: il DTO più il conto che la contiene.</summary>
public sealed record HoldingRow(Holding Item, string AccountName)
{
    public string Ticker => Item.Ticker;
    public decimal Quantity => Item.Quantity;
    public decimal AvgCostBasis => Item.AvgCostBasis;
    public decimal? LastPrice => Item.LastPrice;
    public decimal? MarketValue => Item.MarketValue;
    public decimal? UnrealizedPnl => Item.UnrealizedPnl;
    public string Currency => Item.Currency;
}

/// <summary>Riga della tabella operazioni, con conto e commissioni in chiaro.</summary>
public sealed record OperationRow(StockTransaction Item, string AccountName)
{
    public DateOnly Date => Item.Date;
    public string Type => Item.Type;
    public string Ticker => Item.Ticker;
    public decimal? Quantity => Item.Quantity;
    public decimal? PricePerShare => Item.PricePerShare;
    public decimal Fees => Item.Fees;
    public decimal CashDelta => Item.CashDelta;
    public decimal? RealizedPnl => Item.RealizedPnl;
    public string Currency => Item.Currency;
}

/// <summary>Periodo del grafico e distanza fra due campioni.</summary>
public sealed record RangeOption(string Label, int Days, int IntervalDays)
{
    public override string ToString() => Label;
}

/// <summary>
/// Investimenti (§2.8): posizioni, operazioni, plus/minusvalenze.
///
/// I prezzi arrivano dall'archivio del server, aggiornato una volta al giorno. Senza una
/// chiave API si inseriscono a mano da qui: la pagina resta pienamente usabile.
/// </summary>
public partial class PortfolioViewModel : PageViewModel
{
    public override string Title => "Investimenti";
    public override string Glyph => "▲";

    /// <summary>Voce fittizia in cima alla tendina: aggrega tutti i conti investimento.</summary>
    public static readonly Account AllAccounts = new(
        0, "Tutti i conti", "investment", "EUR", 0, null, null, false, null,
        DateTimeOffset.MinValue, DateTimeOffset.MinValue, 0, null, null);

    public ObservableCollection<Account> AccountOptions { get; } = [];
    public ObservableCollection<Account> WritableAccounts { get; } = [];
    public ObservableCollection<HoldingRow> Holdings { get; } = [];
    public ObservableCollection<OperationRow> Operations { get; } = [];
    public ObservableCollection<TimeseriesPoint> ChartPoints { get; } = [];

    public IReadOnlyList<Models.Currency> Currencies => Models.Currency.All;
    public string[] OperationTypes { get; } = ["buy", "sell", "dividend"];

    /// <summary>
    /// Periodi disponibili. Il passo cresce con la finestra perché lo storico salvato è
    /// giornaliero: su cinque anni un campione al giorno sarebbe illeggibile e inutile.
    /// </summary>
    public RangeOption[] Ranges { get; } =
    [
        new("1 mese", 30, 1),
        new("3 mesi", 90, 1),
        new("6 mesi", 180, 3),
        new("1 anno", 365, 7),
        new("5 anni", 1825, 30),
    ];

    [ObservableProperty] private Account? _selectedAccount;
    [ObservableProperty] private RangeOption? _selectedRange;
    [ObservableProperty] private PortfolioSummary? _summary;
    [ObservableProperty] private bool _showOperations;
    [ObservableProperty] private bool _showPercent;

    // Nuova operazione
    [ObservableProperty] private Account? _operationAccount;
    [ObservableProperty] private string _ticker = string.Empty;
    [ObservableProperty] private string _operationType = "buy";
    [ObservableProperty] private string _quantity = string.Empty;
    [ObservableProperty] private string _pricePerShare = string.Empty;
    [ObservableProperty] private string _fees = "0";
    [ObservableProperty] private string _dividendAmount = string.Empty;
    [ObservableProperty] private Models.Currency _operationCurrency = Models.Currency.All[0];
    [ObservableProperty] private DateTime _operationDate = DateTime.Today;

    [ObservableProperty] private string _priceTicker = string.Empty;
    [ObservableProperty] private string _priceValue = string.Empty;

    public PortfolioViewModel() => _selectedRange = Ranges[1];

    public bool IsDividend => OperationType == "dividend";
    public bool ShowPositions => !ShowOperations;

    /// <summary>La colonna «Conto» serve solo quando si guardano più conti insieme.</summary>
    public bool ShowAccountColumn => SelectedAccount is null || SelectedAccount.Id == 0;

    public string ChartTitle => ShowOperations
        ? "Effetto sulla liquidità, operazione per operazione"
        : "Valore delle posizioni nel tempo";

    public string ValueModeLabel => ShowPercent ? "%" : "€";

    public string UnrealizedDisplay => Format(Summary?.UnrealizedPnl, Summary?.TotalCost);
    public string RealizedDisplay => Format(Summary?.RealizedPnl, Summary?.TotalCost);
    public decimal UnrealizedSign => Summary?.UnrealizedPnl ?? 0;
    public decimal RealizedSign => Summary?.RealizedPnl ?? 0;

    private string Format(decimal? amount, decimal? basis)
    {
        if (amount is null)
        {
            return "—";
        }

        if (!ShowPercent)
        {
            return $"{amount.Value:N2} {Summary?.Currency ?? "EUR"}";
        }

        // Senza costo di carico la percentuale non è definita: meglio un trattino che una
        // divisione per zero travestita da 0%.
        if (basis is null || basis.Value == 0)
        {
            return "—";
        }

        var percent = amount.Value / basis.Value * 100;
        return $"{(percent > 0 ? "+" : string.Empty)}{percent:N2} %";
    }

    public string MissingPricesWarning => Summary is { MissingPrices.Count: > 0 }
        ? "Prezzo non disponibile per: " + string.Join(", ", Summary.MissingPrices) +
          " — valorizzati al costo di carico."
        : string.Empty;

    partial void OnSelectedAccountChanged(Account? value) => _ = RunAsync(LoadPortfolioAsync);
    partial void OnSelectedRangeChanged(RangeOption? value) => _ = RunAsync(LoadChartAsync);
    partial void OnOperationTypeChanged(string value) => OnPropertyChanged(nameof(IsDividend));

    partial void OnShowOperationsChanged(bool value)
    {
        OnPropertyChanged(nameof(ShowPositions));
        OnPropertyChanged(nameof(ChartTitle));
        _ = RunAsync(LoadChartAsync);
    }

    partial void OnShowPercentChanged(bool value)
    {
        OnPropertyChanged(nameof(ValueModeLabel));
        OnPropertyChanged(nameof(UnrealizedDisplay));
        OnPropertyChanged(nameof(RealizedDisplay));
    }

    public override Task LoadAsync() => RunAsync(LoadDataAsync);

    private async Task LoadDataAsync()
    {
        var accounts = await Api.GetAccountsAsync();
        var investment = accounts.Where(a => a.IsInvestment).ToList();

        var previous = SelectedAccount?.Id;
        AccountOptions.Clear();
        WritableAccounts.Clear();
        AccountOptions.Add(AllAccounts);
        foreach (var account in investment)
        {
            AccountOptions.Add(account);
            WritableAccounts.Add(account);
        }

        OperationAccount ??= WritableAccounts.FirstOrDefault();
        SelectedAccount = AccountOptions.FirstOrDefault(a => a.Id == previous) ?? AllAccounts;
        await LoadPortfolioAsync();
    }

    private async Task LoadPortfolioAsync()
    {
        Holdings.Clear();
        Operations.Clear();
        Summary = null;

        var targets = SelectedAccount is null || SelectedAccount.Id == 0
            ? WritableAccounts.ToList()
            : new List<Account> { SelectedAccount };

        if (targets.Count == 0)
        {
            RaiseSummaryChanged();
            return;
        }

        var summaries = new List<PortfolioSummary>();
        foreach (var account in targets)
        {
            var summary = await Api.GetPortfolioAsync(account.Id);
            summaries.Add(summary);

            foreach (var holding in summary.Holdings)
            {
                Holdings.Add(new HoldingRow(holding, account.Name));
            }

            var operations = await Api.GetStockTransactionsAsync(account.Id);
            foreach (var operation in operations.Items)
            {
                Operations.Add(new OperationRow(operation, account.Name));
            }
        }

        Summary = summaries.Count == 1 ? summaries[0] : Aggregate(summaries);
        RaiseSummaryChanged();
        await LoadChartAsync();
    }

    /// <summary>
    /// Somma i riepiloghi di più conti. Regge perché i valori arrivano già espressi nella
    /// valuta del conto; con conti in valute diverse servirebbe una conversione esplicita.
    /// </summary>
    private static PortfolioSummary Aggregate(List<PortfolioSummary> parts) => new(
        0,
        "Tutti i conti",
        parts[0].Currency,
        parts.Sum(p => p.CashBalance),
        parts.Sum(p => p.HoldingsValue),
        parts.Sum(p => p.TotalValue),
        parts.Sum(p => p.TotalCost),
        parts.Sum(p => p.UnrealizedPnl),
        parts.Sum(p => p.RealizedPnl),
        [],
        parts.SelectMany(p => p.MissingPrices).Distinct().ToList());

    private async Task LoadChartAsync()
    {
        ChartPoints.Clear();

        if (ShowOperations)
        {
            // Per le operazioni i campioni sono le operazioni stesse: sono già tutte in
            // locale e non serve scendere alla granularità del giorno.
            foreach (var row in Operations.OrderBy(o => o.Date))
            {
                ChartPoints.Add(new TimeseriesPoint(row.Date, row.CashDelta));
            }
            return;
        }

        var range = SelectedRange ?? Ranges[1];
        int? accountId = SelectedAccount is null || SelectedAccount.Id == 0
            ? null
            : SelectedAccount.Id;

        var history = await Api.GetPortfolioHistoryAsync(accountId, range.Days, range.IntervalDays);
        foreach (var point in history.Points)
        {
            ChartPoints.Add(new TimeseriesPoint(point.Date, point.Value));
        }
    }

    private void RaiseSummaryChanged()
    {
        OnPropertyChanged(nameof(MissingPricesWarning));
        OnPropertyChanged(nameof(UnrealizedDisplay));
        OnPropertyChanged(nameof(RealizedDisplay));
        OnPropertyChanged(nameof(UnrealizedSign));
        OnPropertyChanged(nameof(RealizedSign));
        OnPropertyChanged(nameof(ShowAccountColumn));
    }

    [RelayCommand]
    private void ShowPositionsView() => ShowOperations = false;

    [RelayCommand]
    private void ShowOperationsView() => ShowOperations = true;

    [RelayCommand]
    private void ToggleValueMode() => ShowPercent = !ShowPercent;

    [RelayCommand]
    private Task AddOperation() => RunAsync(async () =>
    {
        var account = OperationAccount
            ?? throw new Services.ApiException("client",
                "Scegli il conto su cui registrare l'operazione.",
                System.Net.HttpStatusCode.BadRequest);

        object payload = IsDividend
            ? new
            {
                account_id = account.Id,
                ticker = Ticker,
                type = "dividend",
                amount = AccountsViewModel.ParseAmount(DividendAmount),
                fees = AccountsViewModel.ParseAmount(Fees),
                currency = OperationCurrency.Code,
                date = DateOnly.FromDateTime(OperationDate).ToString("yyyy-MM-dd")
            }
            : new
            {
                account_id = account.Id,
                ticker = Ticker,
                type = OperationType,
                quantity = AccountsViewModel.ParseAmount(Quantity),
                price_per_share = AccountsViewModel.ParseAmount(PricePerShare),
                fees = AccountsViewModel.ParseAmount(Fees),
                currency = OperationCurrency.Code,
                date = DateOnly.FromDateTime(OperationDate).ToString("yyyy-MM-dd")
            };

        await Api.CreateStockTransactionAsync(payload);
        Quantity = string.Empty;
        PricePerShare = string.Empty;
        DividendAmount = string.Empty;
        await LoadPortfolioAsync();
    }, "Operazione registrata");

    [RelayCommand]
    private Task SetPrice() => RunAsync(async () =>
    {
        await Api.SetPriceAsync(PriceTicker.Trim().ToUpperInvariant(),
            AccountsViewModel.ParseAmount(PriceValue), OperationCurrency.Code);
        PriceValue = string.Empty;
        await LoadPortfolioAsync();
    }, "Prezzo aggiornato");
}
