using System.Text.Json;
using System.Text.Json.Serialization;

namespace Centesimo.Desktop.Services;

/// <summary>
/// Opzioni di serializzazione condivise.
///
/// Due regole non negoziabili del contratto (§1.3):
///   * i nomi dei campi sono snake_case lato API, PascalCase in C#;
///   * gli importi viaggiano come <b>stringhe decimali</b> e in C# sono <c>decimal</c>,
///     mai <c>double</c>: un errore di arrotondamento sui soldi non si recupera.
/// </summary>
public static class ApiJson
{
    public static readonly JsonSerializerOptions Options = Create();

    private static JsonSerializerOptions Create()
    {
        var options = new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
            PropertyNameCaseInsensitive = true,
            NumberHandling = JsonNumberHandling.AllowReadingFromString,
            DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        };
        options.Converters.Add(new DecimalAsStringConverter());
        options.Converters.Add(new NullableDecimalAsStringConverter());
        return options;
    }
}

/// <summary>Legge numeri o stringhe, scrive sempre stringhe (formato invariante).</summary>
public sealed class DecimalAsStringConverter : JsonConverter<decimal>
{
    public override decimal Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
        => reader.TokenType == JsonTokenType.String
            ? decimal.Parse(reader.GetString()!, System.Globalization.CultureInfo.InvariantCulture)
            : reader.GetDecimal();

    public override void Write(Utf8JsonWriter writer, decimal value, JsonSerializerOptions options)
        => writer.WriteStringValue(value.ToString(System.Globalization.CultureInfo.InvariantCulture));
}

public sealed class NullableDecimalAsStringConverter : JsonConverter<decimal?>
{
    public override decimal? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
        => reader.TokenType switch
        {
            JsonTokenType.Null => null,
            JsonTokenType.String => decimal.Parse(reader.GetString()!, System.Globalization.CultureInfo.InvariantCulture),
            _ => reader.GetDecimal()
        };

    public override void Write(Utf8JsonWriter writer, decimal? value, JsonSerializerOptions options)
    {
        if (value is null) writer.WriteNullValue();
        else writer.WriteStringValue(value.Value.ToString(System.Globalization.CultureInfo.InvariantCulture));
    }
}
