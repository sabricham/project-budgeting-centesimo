using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using MoneyApp.Desktop.Models;

namespace MoneyApp.Desktop.ViewModels;

/// <summary>
/// Conti e dettaglio conto (§2.2, §2.3, §2.10): elenco con saldo, storico movimenti,
/// nuova transazione, trasferimento, aggiornamento del residuo per i debiti.
/// </summary>
public partial class AccountsViewModel : PageViewModel
{
    public override string Title => "Conti";
    public override string Glyph => "▤";

    public ObservableCollection<Account> Accounts { get; } = [];
    public ObservableCollection<Transaction> Transactions { get; } = [];
    public ObservableCollection<Category> Categories { get; } = [];

    public string[] AccountTypes { get; } =
        ["bank", "cash", "card", "ewallet", "investment", "savings_goal", "liability"];

    [ObservableProperty]
    private Account? _selectedAccount;

    // --- form "nuova transazione" ---
    [ObservableProperty] private string _newAmount = string.Empty;
    [ObservableProperty] private string _newDescription = string.Empty;
    [ObservableProperty] private DateTime _newDate = DateTime.Today;
    [ObservableProperty] private Category? _newCategory;
    [ObservableProperty] private bool _newIsExpense = true;

    // --- form "nuovo conto" ---
    [ObservableProperty] private string _accountName = string.Empty;
    [ObservableProperty] private string _accountType = "bank";
    [ObservableProperty] private string _accountInitialBalance = "0";

    // --- form "trasferimento" ---
    [ObservableProperty] private Account? _transferFrom;
    [ObservableProperty] private Account? _transferTo;
    [ObservableProperty] private string _transferAmount = string.Empty;
    [ObservableProperty] private DateTime _transferDate = DateTime.Today;

    // --- form "aggiorna residuo debito" (§2.10) ---
    [ObservableProperty] private string _residualAmount = string.Empty;
    [ObservableProperty] private DateTime _residualDate = DateTime.Today;

    public IEnumerable<Category> ExpenseCategories => Categories.Where(c => c.Type == "expense");
    public IEnumerable<Category> IncomeCategories => Categories.Where(c => c.Type == "income");
    public IEnumerable<Category> AvailableCategories => NewIsExpense ? ExpenseCategories : IncomeCategories;

    partial void OnNewIsExpenseChanged(bool value)
    {
        OnPropertyChanged(nameof(AvailableCategories));
        NewCategory = AvailableCategories.FirstOrDefault();
    }

    partial void OnSelectedAccountChanged(Account? value) => _ = RunAsync(LoadTransactionsAsync);

    public override Task LoadAsync() => RunAsync(LoadDataAsync);

    private async Task LoadDataAsync()
    {
        var accounts = await Api.GetAccountsAsync();
        var previous = SelectedAccount?.Id;
        Accounts.Clear();
        foreach (var account in accounts)
        {
            Accounts.Add(account);
        }

        var categories = await Api.GetCategoriesAsync();
        Categories.Clear();
        foreach (var category in categories)
        {
            Categories.Add(category);
        }
        OnPropertyChanged(nameof(AvailableCategories));
        NewCategory ??= AvailableCategories.FirstOrDefault();

        SelectedAccount = Accounts.FirstOrDefault(a => a.Id == previous) ?? Accounts.FirstOrDefault();
        await LoadTransactionsAsync();
    }

    private async Task LoadTransactionsAsync()
    {
        Transactions.Clear();
        if (SelectedAccount is null)
        {
            return;
        }

        var page = await Api.GetTransactionsAsync(SelectedAccount.Id, limit: 200);
        foreach (var transaction in page.Items)
        {
            Transactions.Add(transaction);
        }
    }

    [RelayCommand]
    private Task AddTransaction() => RunAsync(async () =>
    {
        if (SelectedAccount is null || NewCategory is null)
        {
            throw new Services.ApiException("client", "Seleziona conto e categoria.", System.Net.HttpStatusCode.BadRequest);
        }

        var amount = ParseAmount(NewAmount);
        await Api.CreateTransactionAsync(
            SelectedAccount.Id,
            NewCategory.Id,
            NewIsExpense ? "expense" : "income",
            amount,
            DateOnly.FromDateTime(NewDate),
            string.IsNullOrWhiteSpace(NewDescription) ? null : NewDescription);

        NewAmount = string.Empty;
        NewDescription = string.Empty;
        await LoadDataAsync();
    }, "Transazione registrata");

    [RelayCommand]
    private Task AddAccount() => RunAsync(async () =>
    {
        await Api.CreateAccountAsync(AccountName, AccountType, "EUR", ParseAmount(AccountInitialBalance));
        AccountName = string.Empty;
        AccountInitialBalance = "0";
        await LoadDataAsync();
    }, "Conto creato");

    [RelayCommand]
    private Task AddTransfer() => RunAsync(async () =>
    {
        if (TransferFrom is null || TransferTo is null)
        {
            throw new Services.ApiException("client", "Scegli conto di origine e destinazione.", System.Net.HttpStatusCode.BadRequest);
        }

        await Api.CreateTransferAsync(
            TransferFrom.Id, TransferTo.Id, ParseAmount(TransferAmount),
            DateOnly.FromDateTime(TransferDate), null);

        TransferAmount = string.Empty;
        await LoadDataAsync();
    }, "Trasferimento registrato");

    [RelayCommand]
    private Task UpdateResidual() => RunAsync(async () =>
    {
        if (SelectedAccount is null || !SelectedAccount.IsLiability)
        {
            throw new Services.ApiException("client", "Seleziona un conto di tipo debito/prestito.", System.Net.HttpStatusCode.BadRequest);
        }

        await Api.CreateLiabilityUpdateAsync(
            SelectedAccount.Id, ParseAmount(ResidualAmount), DateOnly.FromDateTime(ResidualDate), null);

        ResidualAmount = string.Empty;
        await LoadDataAsync();
    }, "Residuo aggiornato");

    [RelayCommand]
    private Task DeleteTransaction(Transaction? transaction) => transaction is null
        ? Task.CompletedTask
        : RunAsync(async () =>
        {
            await Api.DeleteTransactionAsync(transaction.Id);
            await LoadDataAsync();
        }, "Transazione eliminata");

    [RelayCommand]
    private Task ArchiveAccount(Account? account) => account is null
        ? Task.CompletedTask
        : RunAsync(async () =>
        {
            await Api.ArchiveAccountAsync(account.Id);
            await LoadDataAsync();
        }, "Conto archiviato");

    /// <summary>
    /// Accetta sia "12,34" sia "12.34": l'utente scrive con la virgola, l'API vuole il punto.
    /// La validazione vera resta comunque sul server (§1.3).
    /// </summary>
    internal static decimal ParseAmount(string? text)
    {
        var normalized = (text ?? string.Empty).Trim().Replace(',', '.');
        if (!decimal.TryParse(normalized, System.Globalization.NumberStyles.Number,
                System.Globalization.CultureInfo.InvariantCulture, out var value))
        {
            throw new Services.ApiException("client", $"Importo non valido: '{text}'", System.Net.HttpStatusCode.BadRequest);
        }
        return value;
    }
}
