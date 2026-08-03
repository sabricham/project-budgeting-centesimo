using System.Windows;
using MoneyApp.Desktop.ViewModels;

namespace MoneyApp.Desktop.Views;

public partial class MainWindow : Window
{
    private readonly ShellViewModel _shell = new();

    public MainWindow()
    {
        InitializeComponent();
        DataContext = _shell;
        Loaded += async (_, _) => await _shell.InitializeAsync();
    }

    private async void Logout_Click(object sender, RoutedEventArgs e)
    {
        // Logout vero: il refresh token viene revocato sul server e cancellato
        // dal Credential Manager (§1.1).
        await App.Api.Client.LogoutAsync();
        Application.Current.Shutdown();
    }
}
