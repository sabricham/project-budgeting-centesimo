namespace Centesimo.Desktop.Models;

/// <summary>
/// Valute selezionabili nelle operazioni su titoli.
///
/// L'elenco è **chiuso**: un campo di testo libero accetta "EURO", "eur " o un refuso, e
/// il server lo rifiuta solo dopo il giro di rete — oppure, peggio, lo accetta e i cambi
/// non trovano corrispondenza. Sono le principali valute mondiali per scambi: coprono di
/// fatto tutto ciò su cui si può investire da qui.
/// </summary>
public sealed record Currency(string Code, string Name)
{
    /// <summary>Mostrato nella tendina: "EUR — Euro".</summary>
    public string DisplayName => $"{Code} — {Name}";

    public static readonly IReadOnlyList<Currency> All =
    [
        new("EUR", "Euro"),
        new("USD", "Dollaro statunitense"),
        new("GBP", "Sterlina britannica"),
        new("CHF", "Franco svizzero"),
        new("JPY", "Yen giapponese"),
        new("CNY", "Renminbi cinese"),
        new("CAD", "Dollaro canadese"),
        new("AUD", "Dollaro australiano"),
        new("NZD", "Dollaro neozelandese"),
        new("SEK", "Corona svedese"),
        new("NOK", "Corona norvegese"),
        new("DKK", "Corona danese"),
        new("PLN", "Zloty polacco"),
        new("CZK", "Corona ceca"),
        new("HUF", "Fiorino ungherese"),
        new("HKD", "Dollaro di Hong Kong"),
        new("SGD", "Dollaro di Singapore"),
        new("KRW", "Won sudcoreano"),
        new("INR", "Rupia indiana"),
        new("BRL", "Real brasiliano"),
    ];

    public static Currency Find(string? code) =>
        All.FirstOrDefault(c => string.Equals(c.Code, code, StringComparison.OrdinalIgnoreCase))
        ?? All[0];
}
