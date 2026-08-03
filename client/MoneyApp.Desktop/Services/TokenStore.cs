using System.Runtime.InteropServices;
using System.Text;

namespace MoneyApp.Desktop.Services;

/// <summary>
/// Custodia del refresh token nel <b>Windows Credential Manager</b> (§1.1).
///
/// Il Credential Manager cifra il segreto con DPAPI legandolo all'account Windows: un
/// altro utente della stessa macchina non può rileggerlo. Il refresh token non finisce
/// mai in un file di testo o in un JSON di configurazione, e la password non viene
/// salvata in nessuna forma.
/// </summary>
public sealed class TokenStore
{
    private const string TargetName = "MoneyApp:refresh_token";

    public void Save(string refreshToken, string username)
    {
        var blob = Encoding.UTF8.GetBytes(refreshToken);
        var handle = GCHandle.Alloc(blob, GCHandleType.Pinned);
        try
        {
            var credential = new CREDENTIAL
            {
                Type = CRED_TYPE_GENERIC,
                TargetName = TargetName,
                CredentialBlob = handle.AddrOfPinnedObject(),
                CredentialBlobSize = (uint)blob.Length,
                Persist = CRED_PERSIST_LOCAL_MACHINE,
                UserName = username,
                Comment = "Money App — refresh token"
            };

            if (!CredWrite(ref credential, 0))
            {
                throw new InvalidOperationException(
                    $"Impossibile salvare il token nel Credential Manager (errore {Marshal.GetLastWin32Error()})");
            }
        }
        finally
        {
            handle.Free();
        }
    }

    public (string Token, string Username)? Load()
    {
        if (!CredRead(TargetName, CRED_TYPE_GENERIC, 0, out var pointer))
        {
            return null;
        }

        try
        {
            var credential = Marshal.PtrToStructure<CREDENTIAL>(pointer);
            if (credential.CredentialBlobSize == 0)
            {
                return null;
            }

            var blob = new byte[credential.CredentialBlobSize];
            Marshal.Copy(credential.CredentialBlob, blob, 0, blob.Length);
            return (Encoding.UTF8.GetString(blob), credential.UserName ?? string.Empty);
        }
        finally
        {
            CredFree(pointer);
        }
    }

    public void Clear() => CredDelete(TargetName, CRED_TYPE_GENERIC, 0);

    // --- P/Invoke ---------------------------------------------------------

    private const uint CRED_TYPE_GENERIC = 1;
    private const uint CRED_PERSIST_LOCAL_MACHINE = 2;

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct CREDENTIAL
    {
        public uint Flags;
        public uint Type;
        [MarshalAs(UnmanagedType.LPWStr)] public string TargetName;
        [MarshalAs(UnmanagedType.LPWStr)] public string? Comment;
        public long LastWritten;
        public uint CredentialBlobSize;
        public IntPtr CredentialBlob;
        public uint Persist;
        public uint AttributeCount;
        public IntPtr Attributes;
        [MarshalAs(UnmanagedType.LPWStr)] public string? TargetAlias;
        [MarshalAs(UnmanagedType.LPWStr)] public string? UserName;
    }

    [DllImport("advapi32.dll", EntryPoint = "CredWriteW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool CredWrite(ref CREDENTIAL credential, uint flags);

    [DllImport("advapi32.dll", EntryPoint = "CredReadW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool CredRead(string target, uint type, uint reservedFlag, out IntPtr credentialPtr);

    [DllImport("advapi32.dll", EntryPoint = "CredDeleteW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool CredDelete(string target, uint type, uint flags);

    [DllImport("advapi32.dll", EntryPoint = "CredFree", SetLastError = true)]
    private static extern void CredFree(IntPtr buffer);
}
