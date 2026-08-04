using System.Globalization;
using Centesimo.Desktop.Models;

namespace Centesimo.Desktop.Services;

/// <summary>
/// Facciata tipizzata sugli endpoint: i ViewModel non compongono mai URL a mano.
/// Rispecchia le rotte pubblicate su <c>/openapi.json</c>.
/// </summary>
public sealed class CentesimoApi(ApiClient client)
{
    public ApiClient Client { get; } = client;

    private const string V1 = "api/v1";

    private static string Iso(DateOnly date) => date.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);

    // --- Account utente ----------------------------------------------------

    /// <summary>
    /// Cambia la password. Il server revoca <b>tutte</b> le sessioni, quindi dopo questa
    /// chiamata anche quella corrente non è più valida: chi la usa deve rifare il login.
    /// </summary>
    public Task ChangePasswordAsync(string currentPassword, string newPassword)
        => Client.PostNoContentAsync($"{V1}/auth/change-password", new
        {
            current_password = currentPassword,
            new_password = newPassword
        });

    // --- Impostazioni ------------------------------------------------------

    public Task<MarketDataSettings> GetMarketDataSettingsAsync()
        => Client.GetAsync<MarketDataSettings>($"{V1}/settings/market-data");

    /// <summary>Chiave vuota = lascia invariata quella già salvata sul server.</summary>
    public Task<MarketDataSettings> SaveMarketDataSettingsAsync(
        string provider, string? apiKey, string searchUrl)
        => Client.PutAsync<MarketDataSettings>($"{V1}/settings/market-data", new
        {
            provider,
            api_key = apiKey,
            search_url = searchUrl
        });

    /// <summary>Cancella tutti i dati personali. Irreversibile.</summary>
    public Task<ResetResult> ResetDataAsync(string password, string confirmation)
        => Client.PostAsync<ResetResult>($"{V1}/settings/reset-data", new
        {
            password,
            confirmation
        });

    // --- Conti ------------------------------------------------------------

    public Task<List<Account>> GetAccountsAsync(bool includeArchived = false)
        => Client.GetAsync<List<Account>>($"{V1}/accounts?include_archived={includeArchived.ToString().ToLowerInvariant()}");

    public Task<Account> CreateAccountAsync(string name, string type, string currency, decimal initialBalance, string? notes = null)
        => Client.PostAsync<Account>($"{V1}/accounts", new
        {
            name,
            type,
            currency,
            initial_balance = initialBalance,
            notes
        });

    public Task<Account> UpdateAccountAsync(int id, object payload)
        => Client.PatchAsync<Account>($"{V1}/accounts/{id}", payload);

    public Task ArchiveAccountAsync(int id) => Client.DeleteAsync($"{V1}/accounts/{id}");

    // --- Categorie e budget ------------------------------------------------

    public Task<List<Category>> GetCategoriesAsync(bool includeArchived = false)
        => Client.GetAsync<List<Category>>($"{V1}/categories?include_archived={includeArchived.ToString().ToLowerInvariant()}");

    public Task<Category> CreateCategoryAsync(string name, string type, int? parentId)
        => Client.PostAsync<Category>($"{V1}/categories", new { name, type, parent_category_id = parentId });

    public Task ArchiveCategoryAsync(int id) => Client.DeleteAsync($"{V1}/categories/{id}");

    public Task<List<Budget>> GetBudgetsAsync() => Client.GetAsync<List<Budget>>($"{V1}/budgets");

    public Task<Budget> CreateBudgetAsync(int categoryId, decimal limit)
        => Client.PostAsync<Budget>($"{V1}/budgets", new { category_id = categoryId, amount_limit = limit });

    public Task<Budget> UpdateBudgetAsync(int id, decimal limit)
        => Client.PatchAsync<Budget>($"{V1}/budgets/{id}", new { amount_limit = limit });

    public Task DeleteBudgetAsync(int id) => Client.DeleteAsync($"{V1}/budgets/{id}");

    // --- Transazioni --------------------------------------------------------

    public Task<Page<Transaction>> GetTransactionsAsync(
        int? accountId = null, DateOnly? from = null, DateOnly? to = null, int limit = 100, int offset = 0)
    {
        var query = new List<string> { $"limit={limit}", $"offset={offset}" };
        if (accountId is not null) query.Add($"account_id={accountId}");
        if (from is not null) query.Add($"date_from={Iso(from.Value)}");
        if (to is not null) query.Add($"date_to={Iso(to.Value)}");
        return Client.GetAsync<Page<Transaction>>($"{V1}/transactions?{string.Join("&", query)}");
    }

    public Task<Transaction> CreateTransactionAsync(
        int accountId, int categoryId, string type, decimal amount, DateOnly date, string? description)
        => Client.PostAsync<Transaction>($"{V1}/transactions", new
        {
            account_id = accountId,
            category_id = categoryId,
            type,
            amount,
            date = Iso(date),
            description
        });

    public Task DeleteTransactionAsync(int id) => Client.DeleteAsync($"{V1}/transactions/{id}");

    // --- Trasferimenti ------------------------------------------------------

    public Task<Page<Transfer>> GetTransfersAsync(int limit = 100)
        => Client.GetAsync<Page<Transfer>>($"{V1}/transfers?limit={limit}");

    public Task<Transfer> CreateTransferAsync(int fromId, int toId, decimal amount, DateOnly date, string? description)
        => Client.PostAsync<Transfer>($"{V1}/transfers", new
        {
            from_account_id = fromId,
            to_account_id = toId,
            amount,
            date = Iso(date),
            description
        });

    // --- Debiti -------------------------------------------------------------

    public Task<LiabilityUpdate> CreateLiabilityUpdateAsync(int accountId, decimal residual, DateOnly date, string? note)
        => Client.PostAsync<LiabilityUpdate>($"{V1}/liabilities", new
        {
            account_id = accountId,
            residual_amount = residual,
            date = Iso(date),
            note
        });

    public Task<Page<LiabilityUpdate>> GetLiabilityUpdatesAsync(int accountId)
        => Client.GetAsync<Page<LiabilityUpdate>>($"{V1}/liabilities?account_id={accountId}");

    // --- Obiettivi ----------------------------------------------------------

    public Task<List<Goal>> GetGoalsAsync() => Client.GetAsync<List<Goal>>($"{V1}/goals");

    public Task<Goal> CreateGoalAsync(string name, decimal target, DateOnly? targetDate, int accountId)
        => Client.PostAsync<Goal>($"{V1}/goals", new
        {
            name,
            target_amount = target,
            target_date = targetDate is null ? null : Iso(targetDate.Value),
            linked_account_id = accountId
        });

    public Task DeleteGoalAsync(int id) => Client.DeleteAsync($"{V1}/goals/{id}");

    // --- Ricorrenze ---------------------------------------------------------

    public Task<List<Recurring>> GetRecurringAsync() => Client.GetAsync<List<Recurring>>($"{V1}/recurring");

    public Task<Recurring> CreateRecurringAsync(object payload)
        => Client.PostAsync<Recurring>($"{V1}/recurring", payload);

    public Task DeleteRecurringAsync(int id) => Client.DeleteAsync($"{V1}/recurring/{id}");

    public Task<Page<Transaction>> GetUpcomingAsync(int days = 60)
        => Client.GetAsync<Page<Transaction>>($"{V1}/recurring/upcoming?days={days}");

    public Task<Transaction> ConfirmOccurrenceAsync(int transactionId, decimal? amount)
        => Client.PostAsync<Transaction>($"{V1}/recurring/occurrences/{transactionId}/confirm",
            amount is null ? new { } : new { amount });

    public Task SkipOccurrenceAsync(int transactionId)
        => Client.PostNoContentAsync($"{V1}/recurring/occurrences/{transactionId}/skip");

    // --- Report -------------------------------------------------------------

    public Task<NetWorth> GetNetWorthAsync() => Client.GetAsync<NetWorth>($"{V1}/reports/net-worth");

    public Task<Timeseries> GetTimeseriesAsync(string metric, string range, IEnumerable<int>? accountIds = null)
    {
        var query = $"metric={metric}&range={range}";
        if (accountIds is not null)
        {
            var ids = string.Join(",", accountIds);
            if (ids.Length > 0) query += $"&account_ids={ids}";
        }
        return Client.GetAsync<Timeseries>($"{V1}/reports/timeseries?{query}");
    }

    public Task<CategoryBreakdown> GetBreakdownAsync(string type = "expense", string range = "month")
        => Client.GetAsync<CategoryBreakdown>($"{V1}/reports/by-category?type={type}&range={range}");

    // --- Dashboard ----------------------------------------------------------

    public Task<List<Widget>> GetWidgetsAsync() => Client.GetAsync<List<Widget>>($"{V1}/dashboard/widgets");

    public Task<Widget> CreateWidgetAsync(object payload) => Client.PostAsync<Widget>($"{V1}/dashboard/widgets", payload);

    public Task<Widget> UpdateWidgetAsync(int id, object payload) => Client.PatchAsync<Widget>($"{V1}/dashboard/widgets/{id}", payload);

    public Task DeleteWidgetAsync(int id) => Client.DeleteAsync($"{V1}/dashboard/widgets/{id}");

    // --- Portafoglio --------------------------------------------------------

    /// <summary>
    /// Valore delle posizioni nel tempo. Legge solo l'archivio locale del server, quindi
    /// cambiare periodo o passo non consuma richieste verso il provider.
    /// </summary>
    public Task<PortfolioHistory> GetPortfolioHistoryAsync(
        int? accountId, int days, int intervalDays)
    {
        var query = $"days={days}&interval_days={intervalDays}";
        if (accountId is { } id)
        {
            query += $"&account_id={id}";
        }
        return Client.GetAsync<PortfolioHistory>($"{V1}/portfolio/history?{query}");
    }

    public Task<PortfolioSummary> GetPortfolioAsync(int accountId)
        => Client.GetAsync<PortfolioSummary>($"{V1}/portfolio/{accountId}");

    public Task<Page<StockTransaction>> GetStockTransactionsAsync(int accountId)
        => Client.GetAsync<Page<StockTransaction>>($"{V1}/portfolio/{accountId}/transactions");

    public Task<StockTransaction> CreateStockTransactionAsync(object payload)
        => Client.PostAsync<StockTransaction>($"{V1}/portfolio/transactions", payload);

    public Task<PriceEntry> SetPriceAsync(string ticker, decimal price, string currency)
        => Client.PutAsync<PriceEntry>($"{V1}/portfolio/prices/{ticker}", new { price, currency });

    public Task<Health> GetHealthAsync() => Client.GetAsync<Health>("health");
}
