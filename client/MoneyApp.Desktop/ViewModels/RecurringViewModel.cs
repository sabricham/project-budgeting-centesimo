using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using MoneyApp.Desktop.Models;

namespace MoneyApp.Desktop.ViewModels;

/// <summary>
/// Abbonamenti e spese ricorrenti (§2.7).
///
/// Il campo "giorni" accetta più valori separati da virgola: è il modo in cui si
/// esprimono le <b>più date a calendario</b> nello stesso periodo (es. `1,15`).
/// </summary>
public partial class RecurringViewModel : PageViewModel
{
    public override string Title => "Abbonamenti";
    public override string Glyph => "↻";

    public ObservableCollection<Recurring> Items { get; } = [];
    public ObservableCollection<Transaction> Upcoming { get; } = [];
    public ObservableCollection<Account> Accounts { get; } = [];
    public ObservableCollection<Category> Categories { get; } = [];

    public string[] Frequencies { get; } = ["monthly", "weekly", "yearly", "custom_dates"];

    [ObservableProperty] private Account? _newAccount;
    [ObservableProperty] private Category? _newCategory;
    [ObservableProperty] private string _newDescription = string.Empty;
    [ObservableProperty] private string _newAmount = string.Empty;
    [ObservableProperty] private string _newFrequency = "monthly";
    [ObservableProperty] private string _newDays = "1";
    [ObservableProperty] private int _newInterval = 1;
    [ObservableProperty] private DateTime _newStartDate = DateTime.Today;
    [ObservableProperty] private bool _newAutoConfirm;
    [ObservableProperty] private string _confirmAmount = string.Empty;
    [ObservableProperty] private Transaction? _selectedOccurrence;

    public string DaysHint => NewFrequency switch
    {
        "monthly" => "Giorni del mese, separati da virgola (es. 1,15)",
        "weekly" => "Giorni della settimana 0=lun … 6=dom (es. 0,3)",
        "yearly" => "Coppie mese-giorno (es. 1-1, 7-14)",
        _ => "Date esplicite ISO (es. 2026-03-01, 2026-09-15)"
    };

    partial void OnNewFrequencyChanged(string value) => OnPropertyChanged(nameof(DaysHint));

    public IEnumerable<Category> ExpenseCategories => Categories.Where(c => c.Type == "expense");

    public override Task LoadAsync() => RunAsync(LoadDataAsync);

    private async Task LoadDataAsync()
    {
        var accounts = await Api.GetAccountsAsync();
        Accounts.Clear();
        foreach (var account in accounts.Where(a => !a.IsLiability))
        {
            Accounts.Add(account);
        }
        NewAccount ??= Accounts.FirstOrDefault();

        var categories = await Api.GetCategoriesAsync();
        Categories.Clear();
        foreach (var category in categories)
        {
            Categories.Add(category);
        }
        OnPropertyChanged(nameof(ExpenseCategories));
        NewCategory ??= ExpenseCategories.FirstOrDefault();

        Items.Clear();
        foreach (var item in await Api.GetRecurringAsync())
        {
            Items.Add(item);
        }

        Upcoming.Clear();
        var upcoming = await Api.GetUpcomingAsync(90);
        foreach (var item in upcoming.Items)
        {
            Upcoming.Add(item);
        }
    }

    /// <summary>Traduce il campo di testo nella forma attesa da `occurrence_days` (§2.7).</summary>
    private object[] BuildOccurrenceDays()
    {
        var parts = NewDays.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

        return NewFrequency switch
        {
            "monthly" or "weekly" => parts.Select(p => (object)int.Parse(p)).ToArray(),
            "yearly" => parts.Select(p =>
            {
                var pieces = p.Split('-', StringSplitOptions.RemoveEmptyEntries);
                return (object)new { month = int.Parse(pieces[0]), day = int.Parse(pieces[1]) };
            }).ToArray(),
            _ => parts.Select(p => (object)p).ToArray()
        };
    }

    [RelayCommand]
    private Task AddRecurring() => RunAsync(async () =>
    {
        if (NewAccount is null || NewCategory is null)
        {
            throw new Services.ApiException("client", "Scegli conto e categoria.", System.Net.HttpStatusCode.BadRequest);
        }

        await Api.CreateRecurringAsync(new
        {
            account_id = NewAccount.Id,
            category_id = NewCategory.Id,
            type = NewCategory.Type,
            amount = AccountsViewModel.ParseAmount(NewAmount),
            description = NewDescription,
            frequency = NewFrequency,
            interval = NewInterval,
            occurrence_days = BuildOccurrenceDays(),
            start_date = DateOnly.FromDateTime(NewStartDate).ToString("yyyy-MM-dd"),
            auto_confirm = NewAutoConfirm
        });

        NewAmount = string.Empty;
        NewDescription = string.Empty;
        await LoadDataAsync();
    }, "Ricorrenza creata");

    [RelayCommand]
    private Task DeleteRecurring(Recurring? item) => item is null
        ? Task.CompletedTask
        : RunAsync(async () =>
        {
            await Api.DeleteRecurringAsync(item.Id);
            await LoadDataAsync();
        }, "Ricorrenza disattivata");

    [RelayCommand]
    private Task ConfirmOccurrence(Transaction? occurrence) => occurrence is null
        ? Task.CompletedTask
        : RunAsync(async () =>
        {
            decimal? amount = string.IsNullOrWhiteSpace(ConfirmAmount)
                ? null
                : AccountsViewModel.ParseAmount(ConfirmAmount);
            await Api.ConfirmOccurrenceAsync(occurrence.Id, amount);
            ConfirmAmount = string.Empty;
            await LoadDataAsync();
        }, "Occorrenza confermata");

    [RelayCommand]
    private Task SkipOccurrence(Transaction? occurrence) => occurrence is null
        ? Task.CompletedTask
        : RunAsync(async () =>
        {
            await Api.SkipOccurrenceAsync(occurrence.Id);
            await LoadDataAsync();
        }, "Occorrenza saltata");
}
