using System.Windows;
using Centesimo.Desktop.ViewModels;

namespace Centesimo.Desktop.Views;

public partial class MainWindow : Window
{
    private readonly ShellViewModel _shell = new();

    public MainWindow()
    {
        InitializeComponent();
        DataContext = _shell;
        Loaded += async (_, _) => await _shell.InitializeAsync();
    }

    private async void Settings_Click(object sender, RoutedEventArgs e)
    {
        var settings = new SettingsWindow { Owner = this };
        settings.ShowDialog();

        if (!settings.PasswordChanged)
        {
            return;
        }

        // Il cambio password revoca ogni sessione lato server, compresa questa: restare
        // aperti significherebbe solo collezionare 401 ad ogni richiesta.
        await App.Api.Client.LogoutAsync();
        Application.Current.Shutdown();
    }

    private async void Logout_Click(object sender, RoutedEventArgs e)
    {
        // Logout vero: il refresh token viene revocato sul server e cancellato
        // dal Credential Manager (§1.1).
        await App.Api.Client.LogoutAsync();
        Application.Current.Shutdown();
    }
}
