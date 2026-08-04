using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Centesimo.Desktop.Models;

namespace Centesimo.Desktop.ViewModels;

/// <summary>
/// Portafoglio investimenti (§2.8): posizioni, operazioni, plus/minusvalenze.
///
/// I prezzi arrivano dalla cache del server, aggiornata da un job schedulato. Se non c'è
/// una API key configurata si inseriscono a mano da qui: il portafoglio resta usabile.
/// </summary>
public partial class PortfolioViewModel : PageViewModel
{
    public override string Title => "Portafoglio";
    public override string Glyph => "▲";

    public ObservableCollection<Account> InvestmentAccounts { get; } = [];
    public ObservableCollection<Holding> Holdings { get; } = [];
    public ObservableCollection<StockTransaction> Operations { get; } = [];

    public string[] OperationTypes { get; } = ["buy", "sell", "dividend"];

    [ObservableProperty] private Account? _selectedAccount;
    [ObservableProperty] private PortfolioSummary? _summary;

    [ObservableProperty] private string _ticker = string.Empty;
    [ObservableProperty] private string _operationType = "buy";
    [ObservableProperty] private string _quantity = string.Empty;
    [ObservableProperty] private string _pricePerShare = string.Empty;
    [ObservableProperty] private string _fees = "0";
    [ObservableProperty] private string _dividendAmount = string.Empty;
    [ObservableProperty] private string _currency = "EUR";
    [ObservableProperty] private DateTime _operationDate = DateTime.Today;

    [ObservableProperty] private string _priceTicker = string.Empty;
    [ObservableProperty] private string _priceValue = string.Empty;

    public bool IsDividend => OperationType == "dividend";

    partial void OnOperationTypeChanged(string value) => OnPropertyChanged(nameof(IsDividend));

    partial void OnSelectedAccountChanged(Account? value) => _ = RunAsync(LoadPortfolioAsync);

    public string MissingPricesWarning => Summary is { MissingPrices.Count: > 0 }
        ? $"Prezzo non disponibile per: {string.Join(", ", Summary.MissingPrices)} — valorizzati al costo di carico."
        : string.Empty;

    public override Task LoadAsync() => RunAsync(LoadDataAsync);

    private async Task LoadDataAsync()
    {
        var accounts = await Api.GetAccountsAsync();
        var previous = SelectedAccount?.Id;
        InvestmentAccounts.Clear();
        foreach (var account in accounts.Where(a => a.IsInvestment))
        {
            InvestmentAccounts.Add(account);
        }

        SelectedAccount = InvestmentAccounts.FirstOrDefault(a => a.Id == previous)
                          ?? InvestmentAccounts.FirstOrDefault();
        await LoadPortfolioAsync();
    }

    private async Task LoadPortfolioAsync()
    {
        Holdings.Clear();
        Operations.Clear();
        Summary = null;

        if (SelectedAccount is null)
        {
            OnPropertyChanged(nameof(MissingPricesWarning));
            return;
        }

        Summary = await Api.GetPortfolioAsync(SelectedAccount.Id);
        foreach (var holding in Summary.Holdings)
        {
            Holdings.Add(holding);
        }

        var operations = await Api.GetStockTransactionsAsync(SelectedAccount.Id);
        foreach (var operation in operations.Items)
        {
            Operations.Add(operation);
        }

        OnPropertyChanged(nameof(MissingPricesWarning));
    }

    [RelayCommand]
    private Task AddOperation() => RunAsync(async () =>
    {
        if (SelectedAccount is null)
        {
            throw new Services.ApiException("client",
                "Crea prima un conto di tipo 'Investimenti' dalla pagina Conti.",
                System.Net.HttpStatusCode.BadRequest);
        }

        object payload = IsDividend
            ? new
            {
                account_id = SelectedAccount.Id,
                ticker = Ticker,
                type = "dividend",
                amount = AccountsViewModel.ParseAmount(DividendAmount),
                fees = AccountsViewModel.ParseAmount(Fees),
                currency = Currency,
                date = DateOnly.FromDateTime(OperationDate).ToString("yyyy-MM-dd")
            }
            : new
            {
                account_id = SelectedAccount.Id,
                ticker = Ticker,
                type = OperationType,
                quantity = AccountsViewModel.ParseAmount(Quantity),
                price_per_share = AccountsViewModel.ParseAmount(PricePerShare),
                fees = AccountsViewModel.ParseAmount(Fees),
                currency = Currency,
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
            AccountsViewModel.ParseAmount(PriceValue), Currency);
        PriceValue = string.Empty;
        await LoadPortfolioAsync();
    }, "Prezzo aggiornato");
}
