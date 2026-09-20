using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace Centesimo.Desktop.ViewModels;

/// <summary>Navigazione principale (§2.12).</summary>
public partial class ShellViewModel : ObservableObject
{
    public ShellViewModel()
    {
        Pages = new ObservableCollection<PageViewModel>
        {
            new DashboardViewModel(),
            new AccountsViewModel(),
            new CategoriesViewModel(),
            new RecurringViewModel(),
            new PortfolioViewModel(),
            new GoalsViewModel(),
            new ReportsViewModel(),
        };
        _currentPage = Pages[0];
    }

    public ObservableCollection<PageViewModel> Pages { get; }

    [ObservableProperty]
    private PageViewModel _currentPage;

    public string UserLabel => App.Api.Client.CurrentUser?.DisplayName
                               ?? App.Api.Client.CurrentUser?.Username
                               ?? "utente";

    partial void OnCurrentPageChanged(PageViewModel value)
    {
        _ = value.LoadAsync();
    }

    [RelayCommand]
    private async Task Refresh() => await CurrentPage.LoadAsync();

    public Task InitializeAsync() => CurrentPage.LoadAsync();
}
