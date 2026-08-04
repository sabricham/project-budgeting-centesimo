using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Centesimo.Desktop.Models;

namespace Centesimo.Desktop.ViewModels;

/// <summary>
/// Obiettivi di risparmio (§2.9): si appoggiano a un conto `savings_goal`, il progresso
/// è il saldo di quel conto. Per aumentarlo si fa un trasferimento dalla pagina Conti.
/// </summary>
public partial class GoalsViewModel : PageViewModel
{
    public override string Title => "Obiettivi";
    public override string Glyph => "◎";

    public ObservableCollection<Goal> Goals { get; } = [];
    public ObservableCollection<Account> SavingsAccounts { get; } = [];

    [ObservableProperty] private string _newName = string.Empty;
    [ObservableProperty] private string _newTarget = string.Empty;
    [ObservableProperty] private DateTime? _newTargetDate;
    [ObservableProperty] private Account? _newAccount;

    public override Task LoadAsync() => RunAsync(LoadDataAsync);

    private async Task LoadDataAsync()
    {
        Goals.Clear();
        foreach (var goal in await Api.GetGoalsAsync())
        {
            Goals.Add(goal);
        }

        var accounts = await Api.GetAccountsAsync();
        SavingsAccounts.Clear();
        foreach (var account in accounts.Where(a => a.Type == "savings_goal"))
        {
            SavingsAccounts.Add(account);
        }
        NewAccount ??= SavingsAccounts.FirstOrDefault();
    }

    [RelayCommand]
    private Task AddGoal() => RunAsync(async () =>
    {
        if (NewAccount is null)
        {
            throw new Services.ApiException("client",
                "Serve un conto di tipo 'Risparmio': crealo dalla pagina Conti.",
                System.Net.HttpStatusCode.BadRequest);
        }

        await Api.CreateGoalAsync(
            NewName,
            AccountsViewModel.ParseAmount(NewTarget),
            NewTargetDate is null ? null : DateOnly.FromDateTime(NewTargetDate.Value),
            NewAccount.Id);

        NewName = string.Empty;
        NewTarget = string.Empty;
        await LoadDataAsync();
    }, "Obiettivo creato");

    [RelayCommand]
    private Task DeleteGoal(Goal? goal) => goal is null
        ? Task.CompletedTask
        : RunAsync(async () =>
        {
            await Api.DeleteGoalAsync(goal.Id);
            await LoadDataAsync();
        }, "Obiettivo eliminato");
}
