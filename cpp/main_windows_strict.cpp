#include <windows.h>
#include <shellapi.h>
#include <string>
#include <fstream>
#include <vector>

#define WM_TRAY (WM_APP + 1)
#define ID_TRAY 100
#define ID_DOWNLOAD 200
#define ID_OPEN_LIST 201
#define ID_OPEN_FOLDER 202
#define ID_CHANGE_HOTKEY 203
#define ID_INFO 204
#define ID_EXIT 205

static HINSTANCE g_hInst;
static std::wstring ROOT_DIR;
static std::wstring SYSTEM_DIR;
static std::wstring DOWNLOAD_LIST;
static std::wstring DOWNLOAD_FOLDER;

static UINT HOTKEY_ADD = 1;
static UINT HOTKEY_DOWNLOAD = 2;

static NOTIFYICONDATA nid = {0};

std::wstring GetModuleDir()
{
    wchar_t buf[MAX_PATH];
    GetModuleFileNameW(NULL, buf, MAX_PATH);
    std::wstring path(buf);
    size_t pos = path.find_last_of(L"\\/");
    if (pos != std::wstring::npos)
        path.resize(pos);
    return path;
}

void AddLinkFromClipboard()
{
    if (!OpenClipboard(NULL))
        return;
    HANDLE h = GetClipboardData(CF_UNICODETEXT);
    if (!h)
    {
        CloseClipboard();
        return;
    }
    wchar_t *ptr = static_cast<wchar_t*>(GlobalLock(h));
    if (!ptr)
    {
        CloseClipboard();
        return;
    }
    std::wstring text(ptr);
    GlobalUnlock(h);
    CloseClipboard();

    if (text.empty())
        return;

    std::wofstream file(DOWNLOAD_LIST, std::ios::app);
    if (file.is_open())
        file << text << L"\n";
}

std::vector<std::wstring> ReadList()
{
    std::vector<std::wstring> res;
    std::wifstream f(DOWNLOAD_LIST);
    std::wstring line;
    while (std::getline(f, line))
    {
        if (!line.empty())
            res.push_back(line);
    }
    return res;
}

void ClearList()
{
    std::wofstream f(DOWNLOAD_LIST, std::ios::trunc);
}

void RunDownload(const std::wstring &url)
{
    std::wstring cmd = L"yt-dlp " + url;
    ShellExecuteW(NULL, L"open", L"cmd.exe", (L"/c " + cmd).c_str(), NULL, SW_HIDE);
}

void DownloadAll()
{
    auto urls = ReadList();
    for (const auto &u : urls)
        RunDownload(u);
    ClearList();
}

void ShowInfo()
{
    std::wstring info = SYSTEM_DIR + L"\\info.txt";
    ShellExecuteW(NULL, L"open", info.c_str(), NULL, NULL, SW_SHOWNORMAL);
}

void OpenDownloads()
{
    ShellExecuteW(NULL, L"open", DOWNLOAD_FOLDER.c_str(), NULL, NULL, SW_SHOWNORMAL);
}

void OpenList()
{
    ShellExecuteW(NULL, L"open", DOWNLOAD_LIST.c_str(), NULL, NULL, SW_SHOWNORMAL);
}

void RegisterHotkeys(HWND hwnd)
{
    RegisterHotKey(hwnd, HOTKEY_ADD, MOD_CONTROL, VK_SPACE);
    RegisterHotKey(hwnd, HOTKEY_DOWNLOAD, MOD_CONTROL | MOD_SHIFT, VK_SPACE);
}

void UnregisterHotkeys(HWND hwnd)
{
    UnregisterHotKey(hwnd, HOTKEY_ADD);
    UnregisterHotKey(hwnd, HOTKEY_DOWNLOAD);
}

void AddTrayIcon(HWND hwnd)
{
    nid.cbSize = sizeof(nid);
    nid.hWnd = hwnd;
    nid.uID = ID_TRAY;
    nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP;
    nid.uCallbackMessage = WM_TRAY;
    nid.hIcon = LoadIcon(g_hInst, MAKEINTRESOURCE(1));
    lstrcpyW(nid.szTip, L"YT Downloader");
    Shell_NotifyIconW(NIM_ADD, &nid);
}

void RemoveTrayIcon()
{
    Shell_NotifyIconW(NIM_DELETE, &nid);
    if (nid.hIcon)
        DestroyIcon(nid.hIcon);
}

void ShowMenu(HWND hwnd)
{
    HMENU menu = CreatePopupMenu();
    AppendMenuW(menu, MF_STRING, ID_DOWNLOAD, L"\x0421\x041A\x0410\x0427\x0410\x0422\x042C");
    AppendMenuW(menu, MF_STRING, ID_OPEN_LIST, L"\x0421\x041F\x0418\x0421\x041E\x041A \x0417\x0410\x0413\x0420\x0423\x0417\x041E\x041A");
    AppendMenuW(menu, MF_STRING, ID_OPEN_FOLDER, L"\x041F\x0410\x041F\x041A\x0410 \x0417\x0410\x0413\x0420\x0423\x0417\x041A\x0418");
    AppendMenuW(menu, MF_STRING, ID_INFO, L"INFO");
    AppendMenuW(menu, MF_STRING, ID_EXIT, L"\x0412\x042B\x0425\x041E\x0414");

    POINT pt;
    GetCursorPos(&pt);
    SetForegroundWindow(hwnd);
    TrackPopupMenu(menu, TPM_RIGHTBUTTON, pt.x, pt.y, 0, hwnd, NULL);
    DestroyMenu(menu);
}

LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wParam, LPARAM lParam)
{
    switch (msg)
    {
    case WM_HOTKEY:
        if (wParam == HOTKEY_ADD)
            AddLinkFromClipboard();
        else if (wParam == HOTKEY_DOWNLOAD)
            DownloadAll();
        break;
    case WM_COMMAND:
        switch (LOWORD(wParam))
        {
        case ID_DOWNLOAD: DownloadAll(); break;
        case ID_OPEN_LIST: OpenList(); break;
        case ID_OPEN_FOLDER: OpenDownloads(); break;
        case ID_INFO: ShowInfo(); break;
        case ID_EXIT: PostQuitMessage(0); break;
        }
        break;
    case WM_TRAY:
        if (lParam == WM_RBUTTONUP)
            ShowMenu(hwnd);
        break;
    case WM_DESTROY:
        UnregisterHotkeys(hwnd);
        RemoveTrayIcon();
        PostQuitMessage(0);
        break;
    default:
        return DefWindowProc(hwnd, msg, wParam, lParam);
    }
    return 0;
}

int WINAPI wWinMain(HINSTANCE hInstance, HINSTANCE, PWSTR, int)
{
    g_hInst = hInstance;
    ROOT_DIR = GetModuleDir();
    SYSTEM_DIR = ROOT_DIR + L"\\system";
    DOWNLOAD_LIST = SYSTEM_DIR + L"\\download-list.txt";
    DOWNLOAD_FOLDER = ROOT_DIR + L"\\Downloads";
    WNDCLASSW wc = {0};
    wc.lpfnWndProc = WndProc;
    wc.hInstance = hInstance;
    wc.lpszClassName = L"TrayWnd";
    RegisterClassW(&wc);
    HWND hwnd = CreateWindowExW(0, wc.lpszClassName, L"YTDownloader", 0, 0,0,0,0, NULL, NULL, hInstance, NULL);
    RegisterHotkeys(hwnd);
    AddTrayIcon(hwnd);

    MSG msg;
    while (GetMessageW(&msg, NULL, 0, 0))
    {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
    return 0;
}

