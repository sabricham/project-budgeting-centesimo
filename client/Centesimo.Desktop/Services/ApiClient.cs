using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Http.Json;
using System.Security.Cryptography.X509Certificates;
using System.Text.Json;
using Centesimo.Desktop.Models;

namespace Centesimo.Desktop.Services;

public sealed class ApiException : Exception
{
    public ApiException(string code, string message, HttpStatusCode statusCode) : base(message)
    {
        Code = code;
        StatusCode = statusCode;
    }

    public string Code { get; }
    public HttpStatusCode StatusCode { get; }
}

/// <summary>
/// Unico punto di contatto con il backend (§0: nessun accesso diretto al DB).
///
/// Comportamenti chiave:
///   * access token in memoria, refresh token nel Credential Manager;
///   * al primo 401 tenta un refresh trasparente e ripete la richiesta una sola volta;
///   * il certificato self-signed viene accettato solo se coincide con quello pinnato
///     (§1.1): la verifica TLS non viene mai disattivata.
/// </summary>
public sealed class ApiClient : IDisposable
{
    private readonly HttpClient _http;
    private readonly TokenStore _tokens;
    private readonly SemaphoreSlim _refreshLock = new(1, 1);

    private string? _accessToken;
    private string? _refreshToken;

    public ApiClient(AppSettings settings, TokenStore tokens)
    {
        Settings = settings;
        _tokens = tokens;

        var handler = new HttpClientHandler
        {
            ServerCertificateCustomValidationCallback = BuildCertificateValidator(settings)
        };

        _http = new HttpClient(handler)
        {
            BaseAddress = new Uri(settings.ApiBaseUrl.TrimEnd('/') + "/"),
            Timeout = TimeSpan.FromSeconds(30)
        };
    }

    public AppSettings Settings { get; }
    public UserInfo? CurrentUser { get; private set; }
    public bool IsAuthenticated => _accessToken is not null;

    private static Func<HttpRequestMessage, X509Certificate2?, X509Chain?, System.Net.Security.SslPolicyErrors, bool>
        BuildCertificateValidator(AppSettings settings)
    {
        X509Certificate2? pinned = null;
        if (!string.IsNullOrWhiteSpace(settings.ServerCertificatePath) &&
            File.Exists(settings.ServerCertificatePath))
        {
            try
            {
                pinned = X509CertificateLoader.LoadCertificateFromFile(settings.ServerCertificatePath);
            }
            catch (Exception)
            {
                pinned = null;
            }
        }

        return (_, certificate, _, errors) =>
        {
            if (errors == System.Net.Security.SslPolicyErrors.None)
            {
                return true;
            }

            // Unica eccezione ammessa: è esattamente il certificato che ci aspettiamo.
            return pinned is not null && certificate is not null &&
                   certificate.RawData.AsSpan().SequenceEqual(pinned.RawData);
        };
    }

    // --- Autenticazione ---------------------------------------------------

    public async Task<UserInfo> LoginAsync(string username, string password, CancellationToken ct = default)
    {
        var response = await _http.PostAsJsonAsync(
            "api/v1/auth/login",
            new { username, password, client_info = Environment.MachineName },
            ApiJson.Options, ct);

        var pair = await ReadAsync<TokenPair>(response, ct);
        _accessToken = pair.AccessToken;
        _refreshToken = pair.RefreshToken;
        _tokens.Save(pair.RefreshToken, username);

        CurrentUser = await GetAsync<UserInfo>("api/v1/auth/me", ct);
        return CurrentUser;
    }

    /// <summary>Riapre la sessione dal refresh token salvato, senza chiedere la password.</summary>
    public async Task<UserInfo?> TryRestoreSessionAsync(CancellationToken ct = default)
    {
        var stored = _tokens.Load();
        if (stored is null)
        {
            return null;
        }

        _refreshToken = stored.Value.Token;
        if (!await TryRefreshAsync(ct))
        {
            return null;
        }

        try
        {
            CurrentUser = await GetAsync<UserInfo>("api/v1/auth/me", ct);
            return CurrentUser;
        }
        catch (ApiException)
        {
            return null;
        }
    }

    public async Task LogoutAsync(CancellationToken ct = default)
    {
        if (_refreshToken is not null)
        {
            try
            {
                await _http.PostAsJsonAsync("api/v1/auth/logout",
                    new { refresh_token = _refreshToken }, ApiJson.Options, ct);
            }
            catch (HttpRequestException)
            {
                // offline: il token locale va comunque buttato
            }
        }

        _accessToken = null;
        _refreshToken = null;
        CurrentUser = null;
        _tokens.Clear();
    }

    private async Task<bool> TryRefreshAsync(CancellationToken ct)
    {
        if (_refreshToken is null)
        {
            return false;
        }

        await _refreshLock.WaitAsync(ct);
        try
        {
            var response = await _http.PostAsJsonAsync("api/v1/auth/refresh",
                new { refresh_token = _refreshToken }, ApiJson.Options, ct);

            if (!response.IsSuccessStatusCode)
            {
                _accessToken = null;
                _refreshToken = null;
                _tokens.Clear();
                return false;
            }

            var pair = await response.Content.ReadFromJsonAsync<TokenPair>(ApiJson.Options, ct);
            if (pair is null)
            {
                return false;
            }

            _accessToken = pair.AccessToken;
            _refreshToken = pair.RefreshToken;
            // Rotazione lato server: il vecchio refresh token è già revocato.
            _tokens.Save(pair.RefreshToken, CurrentUser?.Username ?? string.Empty);
            return true;
        }
        catch (HttpRequestException)
        {
            return false;
        }
        finally
        {
            _refreshLock.Release();
        }
    }

    // --- Verbi ------------------------------------------------------------

    public Task<T> GetAsync<T>(string path, CancellationToken ct = default)
        => SendAsync<T>(HttpMethod.Get, path, null, ct);

    public Task<T> PostAsync<T>(string path, object? body, CancellationToken ct = default)
        => SendAsync<T>(HttpMethod.Post, path, body, ct);

    public Task<T> PatchAsync<T>(string path, object? body, CancellationToken ct = default)
        => SendAsync<T>(HttpMethod.Patch, path, body, ct);

    public Task<T> PutAsync<T>(string path, object? body, CancellationToken ct = default)
        => SendAsync<T>(HttpMethod.Put, path, body, ct);

    public async Task DeleteAsync(string path, CancellationToken ct = default)
        => await SendRawAsync(HttpMethod.Delete, path, null, ct);

    public async Task PostNoContentAsync(string path, object? body = null, CancellationToken ct = default)
        => await SendRawAsync(HttpMethod.Post, path, body, ct);

    private async Task<T> SendAsync<T>(HttpMethod method, string path, object? body, CancellationToken ct)
    {
        var response = await SendRawAsync(method, path, body, ct);
        return await ReadAsync<T>(response, ct);
    }

    private async Task<HttpResponseMessage> SendRawAsync(
        HttpMethod method, string path, object? body, CancellationToken ct)
    {
        var response = await SendOnceAsync(method, path, body, ct);

        if (response.StatusCode == HttpStatusCode.Unauthorized && _refreshToken is not null)
        {
            response.Dispose();
            if (await TryRefreshAsync(ct))
            {
                response = await SendOnceAsync(method, path, body, ct);
            }
            else
            {
                throw new ApiException("session_expired",
                    "Sessione scaduta: effettua di nuovo il login.", HttpStatusCode.Unauthorized);
            }
        }

        if (!response.IsSuccessStatusCode)
        {
            throw await BuildExceptionAsync(response, ct);
        }

        return response;
    }

    private async Task<HttpResponseMessage> SendOnceAsync(
        HttpMethod method, string path, object? body, CancellationToken ct)
    {
        using var request = new HttpRequestMessage(method, path);
        if (body is not null)
        {
            request.Content = JsonContent.Create(body, options: ApiJson.Options);
        }

        if (_accessToken is not null)
        {
            request.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", _accessToken);
        }

        return await _http.SendAsync(request, ct);
    }

    private static async Task<T> ReadAsync<T>(HttpResponseMessage response, CancellationToken ct)
    {
        if (!response.IsSuccessStatusCode)
        {
            throw await BuildExceptionAsync(response, ct);
        }

        var value = await response.Content.ReadFromJsonAsync<T>(ApiJson.Options, ct);
        return value ?? throw new ApiException("empty_response", "Risposta vuota dal server.", response.StatusCode);
    }

    private static async Task<ApiException> BuildExceptionAsync(HttpResponseMessage response, CancellationToken ct)
    {
        try
        {
            var body = await response.Content.ReadFromJsonAsync<ApiErrorBody>(ApiJson.Options, ct);
            if (body?.Error is not null)
            {
                return new ApiException(body.Error.Code, body.Error.Message, response.StatusCode);
            }
        }
        catch (Exception)
        {
            // il corpo non era nel formato d'errore atteso
        }

        return new ApiException("http_error",
            $"Errore {(int)response.StatusCode} dal server.", response.StatusCode);
    }

    public void Dispose()
    {
        _http.Dispose();
        _refreshLock.Dispose();
    }
}
