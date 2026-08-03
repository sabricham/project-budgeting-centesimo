using System.Text.Json.Serialization;

namespace MoneyApp.Desktop.Models;

// I DTO rispecchiano 1:1 gli schemi Pydantic del server (vedi /openapi.json).
// Gli importi sono `decimal`, mai double/float (§1.3): la conversione da/verso stringa
// decimale è gestita da DecimalAsStringConverter in ApiJson.

public record TokenPair(
    string AccessToken,
    string RefreshToken,
    string TokenType,
    int ExpiresIn);

public record UserInfo(int Id, string Username, string? DisplayName, string BaseCurrency);

public record Health(string Status, string Db, string Version, string Scheduler);

public record Account(
    int Id,
    string Name,
    string Type,
    string Currency,
    decimal InitialBalance,
    string? Icon,
    string? Color,
    bool Archived,
    string? Notes,
    DateTimeOffset CreatedAt,
    DateTimeOffset UpdatedAt,
    decimal Balance,
    decimal? CashBalance,
    decimal? HoldingsValue)
{
    [JsonIgnore]
    public string TypeLabel => Type switch
    {
        "bank" => "Conto bancario",
        "cash" => "Contanti",
        "card" => "Carta",
        "ewallet" => "Portafoglio elettronico",
        "investment" => "Investimenti",
        "savings_goal" => "Risparmio",
        "liability" => "Debito/Prestito",
        _ => Type
    };

    [JsonIgnore]
    public bool IsLiability => Type == "liability";

    [JsonIgnore]
    public bool IsInvestment => Type == "investment";
}

public record Category(
    int Id,
    string Name,
    string Type,
    int? ParentCategoryId,
    string? Icon,
    string? Color,
    bool Archived,
    DateTimeOffset CreatedAt,
    DateTimeOffset UpdatedAt)
{
    [JsonIgnore]
    public string DisplayName => ParentCategoryId is null ? Name : "    " + Name;
}

public record Budget(
    int Id,
    int CategoryId,
    string CategoryName,
    decimal AmountLimit,
    bool Active,
    decimal SpentThisMonth,
    decimal Remaining,
    double UsageRatio,
    DateTimeOffset CreatedAt,
    DateTimeOffset UpdatedAt)
{
    [JsonIgnore]
    public double UsagePercent => Math.Min(UsageRatio, 1.0) * 100;

    [JsonIgnore]
    public bool OverBudget => Remaining < 0;
}

public record Transaction(
    int Id,
    int AccountId,
    string? AccountName,
    int CategoryId,
    string? CategoryName,
    string Type,
    decimal Amount,
    DateOnly Date,
    string? Description,
    string Status,
    int? SourceRecurringId,
    DateTimeOffset CreatedAt,
    DateTimeOffset UpdatedAt)
{
    [JsonIgnore]
    public decimal SignedAmount => Type == "expense" ? -Amount : Amount;

    [JsonIgnore]
    public bool IsProjected => Status == "projected";
}

public record Transfer(
    int Id,
    int FromAccountId,
    string? FromAccountName,
    int ToAccountId,
    string? ToAccountName,
    decimal Amount,
    DateOnly Date,
    string? Description,
    DateTimeOffset CreatedAt,
    DateTimeOffset UpdatedAt);

public record LiabilityUpdate(
    int Id,
    int AccountId,
    decimal ResidualAmount,
    DateOnly Date,
    string? Note,
    DateTimeOffset CreatedAt,
    DateTimeOffset UpdatedAt);

public record Goal(
    int Id,
    string Name,
    decimal TargetAmount,
    DateOnly? TargetDate,
    int LinkedAccountId,
    string? LinkedAccountName,
    string? Icon,
    string? Color,
    decimal CurrentAmount,
    double Progress,
    decimal? MonthlyRequired,
    int? MonthsRemaining,
    DateTimeOffset CreatedAt,
    DateTimeOffset UpdatedAt)
{
    [JsonIgnore]
    public double ProgressPercent => Math.Min(Progress, 1.0) * 100;
}

public record Recurring(
    int Id,
    int AccountId,
    string? AccountName,
    int CategoryId,
    string? CategoryName,
    string Type,
    decimal Amount,
    string? Description,
    string Frequency,
    int Interval,
    List<object> OccurrenceDays,
    DateOnly StartDate,
    DateOnly? EndDate,
    bool Active,
    bool AutoConfirm,
    DateOnly? NextOccurrence,
    DateTimeOffset CreatedAt,
    DateTimeOffset UpdatedAt);

public record Holding(
    int Id,
    int AccountId,
    string Ticker,
    decimal Quantity,
    decimal AvgCostBasis,
    string Currency,
    decimal? LastPrice,
    DateTimeOffset? PriceFetchedAt,
    string? PriceSource,
    decimal? MarketValue,
    decimal CostValue,
    decimal? UnrealizedPnl,
    double? UnrealizedPnlPct);

public record PortfolioSummary(
    int AccountId,
    string AccountName,
    string Currency,
    decimal CashBalance,
    decimal HoldingsValue,
    decimal TotalValue,
    decimal TotalCost,
    decimal UnrealizedPnl,
    decimal RealizedPnl,
    List<Holding> Holdings,
    List<string> MissingPrices);

public record StockTransaction(
    int Id,
    int AccountId,
    string Ticker,
    string Type,
    decimal? Quantity,
    decimal? PricePerShare,
    decimal Fees,
    decimal? Amount,
    string Currency,
    DateOnly Date,
    string? Notes,
    decimal? RealizedPnl,
    decimal CashDelta,
    DateTimeOffset CreatedAt);

public record NetWorth
{
    public string Currency { get; init; } = "EUR";
    public decimal Assets { get; init; }
    public decimal Liabilities { get; init; }

    /// <summary>Il campo JSON è `net_worth`; in C# non può chiamarsi come il tipo.</summary>
    [JsonPropertyName("net_worth")]
    public decimal Total { get; init; }

    public DateOnly AsOf { get; init; }
}

public record TimeseriesPoint(DateOnly Bucket, decimal Value);

public record Timeseries(
    string Metric,
    string Range,
    string Currency,
    DateOnly DateFrom,
    DateOnly DateTo,
    List<TimeseriesPoint> Points);

public record CategoryBreakdownItem(
    int CategoryId,
    string CategoryName,
    int? ParentCategoryId,
    decimal Total,
    double Share);

public record CategoryBreakdown(
    string Type,
    DateOnly DateFrom,
    DateOnly DateTo,
    string Currency,
    decimal Total,
    List<CategoryBreakdownItem> Items);

public record Widget(
    int Id,
    string Type,
    int PositionX,
    int PositionY,
    int Width,
    int Height,
    Dictionary<string, object> Config,
    DateTimeOffset CreatedAt,
    DateTimeOffset UpdatedAt);

public record Page<T>(List<T> Items, int Total, int Limit, int Offset);

public record PriceEntry(string Ticker, decimal Price, string Currency, DateTimeOffset FetchedAt, string Source);

/// <summary>Errore restituito dall'API nel formato `{"error": {"code", "message"}}` (§1.2).</summary>
public record ApiErrorBody(ApiErrorDetail Error);

public record ApiErrorDetail(string Code, string Message);
