"""Windows CurrentUser DPAPI credentials; plaintext never enters command output."""
import ctypes
import os
from ctypes import wintypes
from pathlib import Path


def load_secret(root,name):
    if os.name!='nt':
        import keyring
        value=keyring.get_password('instagram-auto-post',name)
        if not value:raise ValueError('시스템 키체인에 인증 정보를 저장해 주세요')
        return value
    if name not in ('instagram-token','cloudinary'):raise ValueError('등록되지 않은 인증 파일')
    try:encrypted=bytes.fromhex((Path(root)/'data/runtime/credentials'/f'{name}.dpapi').read_text(encoding='utf-8-sig').strip())
    except (OSError,ValueError):raise ValueError('암호화 인증 파일 확인 필요') from None
    class Blob(ctypes.Structure):
        _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]
    buffer=(ctypes.c_ubyte*len(encrypted)).from_buffer_copy(encrypted)
    source=Blob(len(encrypted),buffer);target=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True)
    crypt.CryptUnprotectData.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    crypt.CryptUnprotectData.restype=wintypes.BOOL
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
    if not crypt.CryptUnprotectData(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):raise ValueError('현재 Windows 사용자에서 인증 복호화 실패')
    try:return ctypes.string_at(target.data,target.size).decode('utf-16-le')
    finally:
        ctypes.memset(target.data,0,target.size);kernel.LocalFree(target.data)
