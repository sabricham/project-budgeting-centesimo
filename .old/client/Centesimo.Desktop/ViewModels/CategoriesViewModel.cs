using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Centesimo.Desktop.Models;

namespace Centesimo.Desktop.ViewModels;

/// <summary>
/// Categorie e budget mensili (§2.4, §2.5).
/// `spent_this_month` e `remaining` arrivano già calcolati dal server: il client non
/// ricalcola nulla, così il valore è identico ovunque venga mostrato.
/// </summary>
public partial class CategoriesViewModel : PageViewModel
{
    public override string Title => "Categorie e budget";
    public override string Glyph => "◈";

    public ObservableCollection<Category> Categories { get; } = [];
    public ObservableCollection<Budget> Budgets { get; } = [];

    public string[] CategoryTypes { get; } = ["expense", "income"];

    [ObservableProperty] private string _newCategoryName = string.Empty;
    [ObservableProperty] private string _newCategoryType = "expense";
    [ObservableProperty] private Category? _newCategoryParent;

    [ObservableProperty] private Category? _budgetCategory;
    [ObservableProperty] private string _budgetLimit = string.Empty;

    public IEnumerable<Category> PossibleParents =>
        Categories.Where(c => c.ParentCategoryId is null && c.Type == NewCategoryType);

    public IEnumerable<Category> ExpenseCategories => Categories.Where(c => c.Type == "expense");

    partial void OnNewCategoryTypeChanged(string value) => OnPropertyChanged(nameof(PossibleParents));

    public override Task LoadAsync() => RunAsync(LoadDataAsync);

    private async Task LoadDataAsync()
    {
        var categories = await Api.GetCategoriesAsync();
        Categories.Clear();
        foreach (var category in categories)
        {
            Categories.Add(category);
        }
        OnPropertyChanged(nameof(PossibleParents));
        OnPropertyChanged(nameof(ExpenseCategories));

        var budgets = await Api.GetBudgetsAsync();
        Budgets.Clear();
        foreach (var budget in budgets)
        {
            Budgets.Add(budget);
        }
    }

    [RelayCommand]
    private Task AddCategory() => RunAsync(async () =>
    {
        await Api.CreateCategoryAsync(NewCategoryName, NewCategoryType, NewCategoryParent?.Id);
        NewCategoryName = string.Empty;
        NewCategoryParent = null;
        await LoadDataAsync();
    }, "Categoria creata");

    [RelayCommand]
    private Task ArchiveCategory(Category? category) => category is null
        ? Task.CompletedTask
        : RunAsync(async () =>
        {
            await Api.ArchiveCategoryAsync(category.Id);
            await LoadDataAsync();
        }, "Categoria archiviata");

    [RelayCommand]
    private Task AddBudget() => RunAsync(async () =>
    {
        if (BudgetCategory is null)
        {
            throw new Services.ApiException("client", "Scegli una categoria di spesa.", System.Net.HttpStatusCode.BadRequest);
        }

        await Api.CreateBudgetAsync(BudgetCategory.Id, AccountsViewModel.ParseAmount(BudgetLimit));
        BudgetLimit = string.Empty;
        await LoadDataAsync();
    }, "Budget impostato");

    [RelayCommand]
    private Task DeleteBudget(Budget? budget) => budget is null
        ? Task.CompletedTask
        : RunAsync(async () =>
        {
            await Api.DeleteBudgetAsync(budget.Id);
            await LoadDataAsync();
        }, "Budget rimosso");
}
