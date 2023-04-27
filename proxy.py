
import socket
import tkinter as tk
import tkinter.messagebox as tkmsg

import logger
import rsglobal
import datetime
import time
import json
import os
import threading
import traceback

class Status:

    NULL = b"\x00"
    OK = b"\x01"
    JSON = b"\x02"
    NO_PERM = b"\x11"
    NO_AUTH = b"\x10"
    INTERNAL_ERR = b"\xa0"

class Reader:

    def __init__(self, data=b""):
        self.data = data
        self.pointer = 0

    def readServerCode(self):
        b = self.readByte()
        if b == 0x00:
            return "T"
        elif b == 0x01:
            return "S"
        elif b == 0x02:
            return "M"
        elif b == 0x03:
            return "B"
        elif b == 0x04:
            return "G"

    def readByte(self):
        x = self.data[self.pointer]
        self.pointer += 1
        if isinstance(x, int):
            return x
        return ord(x)
                         
    def readShort(self):
        n = 0
        for i in range(2):
            n += self.readByte() * 256 ** i
        return n
    

    def readSignedShort(self):
        return self.readShort() - 32768

    def readInteger(self):
        n = 0
        for i in range(4):
            n += self.readByte() * 256 ** i
        return n

    def readLong(self):
        n = 0
        for i in range(8):
            n += self.readByte() * 256 ** i
        return n

    def readSignedLong(self):
        return self.readLong() - 9223372036854775808

    def readSignedInteger(self):
        return self.readInteger() - 2147483648

    def readString(self):
        size = self.readShort()
        x = ""
        for i in range(size):
            x += chr(self.readByte())
        return x

    def readBoolean(self):
        if self.readByte():
            return True
        return False

    def readTypeArray(self):
        typ_i = self.readByte()
        typ = self.types[typ_i]
        size = self.readShort()
        arr = []
        for i in range(size):
            arr.append(typ(self))
        return arr

    def readMixedArray(self):
        size = self.readShort()
        arr = []
        for i in range(size):
            typ_i = self.readByte()
            typ = self.types[typ_i]
            arr.append(typ(self))
        return arr

    def writeByte(self, b):
        self.data += bytes(chr(b).encode("latin-1"))

    def writeShort(self, s):
        if s > 65535:
            raise TypeError("s must < 65536!")
        if s < 0:
            raise TypeError("s must >= 0! Otherwise use writeSignedShort")
        for i in range(2):
            b = int(s % 256)
            self.writeByte(b)
            s = (s - b) / 256

    def writeSignedShort(self, s):
        if s > 32767:
            raise TypeError("s must < 32767! Otherwise use writeShort!")
        if s < -32768:
            raise TypeError("s must >= -32768!")
        s += 32768
        self.writeShort(s)

    def writeString(self, s):
        if len(s) > 65535:
            raise TypeError("String is too long! Max len is 65535!")
        self.writeShort(len(s))
        for i in s:
            self.writeByte(ord(i))

    def writePureBytes(self, b):
        self.data += b

    types = {
        0: readByte,
        1: readShort,
        2: readSignedShort,
        3: readInteger,
        4: readSignedInteger,
        5: readString,
        6: readTypeArray,
        7: readMixedArray,
        8: readBoolean
    }

class OutPacket:

    def __init__(self, typebyte):
        self.data = b""
        self.writeByte(typebyte)

    def writeByte(self, b):
        self.data += bytes(chr(b).encode("latin-1"))

    def writeShort(self, s):
        if s > 65535:
            raise TypeError("s must < 65536!")
        if s < 0:
            raise TypeError("s must >= 0! Otherwise use writeSignedShort")
        for i in range(2):
            b = int(s % 256)
            self.writeByte(b)
            s = (s - b) / 256

    def writeInteger(self, i):
        if s > 2147483647:
            raise TypeError("s must < 2147483647!")
        if s < 0:
            raise TypeError("s must >= 0! Otherwise use writeSignedInteger")
        for i in range(4):
            b = int(s % 256)
            self.writeByte(b)
            s = (s - b) / 256

    def writeSignedShort(self, s):
        if s > 32767:
            raise TypeError("s must < 32767! Otherwise use writeShort!")
        if s < -32768:
            raise TypeError("s must >= -32768!")
        s += 32768
        self.writeShort(s)

    def writeString(self, s):
        if len(s) > 65535:
            raise TypeError("String is too long! Max len is 65535!")
        self.writeShort(len(s))
        for i in s:
            self.writeByte(ord(i))

    def writeTypeArray(self, a):
        if len(a) == None:
            self.writeByte(0)
            self.writeShort(0)
            return
        first = True
        for i in a:
            if first:
                self.writeByteType(i)
                self.writeShort(len(a))
                first = False
            self.writeByObjectClass(i)

    def writeMixedArray(self, a):
        self.writeShort(len(a))
        if len(a) == 0:
            return
        for i in a:
            self.writeByteType(i)
            self.writeByObjectClass(i)
                

    def writeByteType(self, obj):
        if isinstance(obj, bytes):
            self.writeByte(0x00)
        elif isinstance(obj, int):
            if obj < 65536:
                self.writeByte(0x01)
            elif obj < 2147483648:
                self.writeByte(0x03)
        elif isinstance(obj, list):
            self.writeByte(0x07)
        elif isinstance(obj, str):
            self.writeByte(0x05)

    def writeByObjectClass(self, obj):
        if isinstance(obj, bytes):
            self.writeByte(obj)
        elif isinstance(obj, int):
            if obj < 65536:
                self.writeShort(obj)
            elif obj < 2147483648:
                self.writeInt(obj)
        elif isinstance(obj, list):
            self.writeMixedArray(obj)
        elif isinstance(obj, str):
            self.writeString(obj)


class OutPacketGroup:

    def __init__(self, group):
        self.group = group
        self.data = Reader()
        self.data.writeShort(len(group))
        for i in self.group:
            self.data.writeShort(len(i.data))
            self.data.writePureBytes(i.data)
        
        

class ProxyListener:

    def __init__(self, servers, server_list, opened_details, bungee):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind(("127.0.0.1", 127))
        self.socket.listen()
        self.servers = servers
        self.server_list = server_list
        self.bungee = bungee
        self.opened_details = opened_details
        self.LOG = logger.Logger(self)
        self.awaitWarps = []

        while True:
            #print('waiting for connection...')
            con, addr = self.socket.accept()
            data = con.recv(1024)
            #print(f"data: {data}, addr: {addr}")

            packet = Reader(data)
            typ = packet.readByte()
            try:
                if typ == 1:
                    ram = packet.readByte()
                    temp = packet.readString()
                    idd = packet.readString()
                    name = packet.readString()
                    svtype = packet.readString()
                    port = packet.readShort()
                    for i in self.server_list:
                        if i.id == idd:
                            print(i.name, name)
                            #i.name = name
                            i.status = rsglobal.SERVER_STATUS.RUNNING
                            break
                    else:
                        srv = rsglobal.DynamicServer(temp, rsglobal.SERVER_RAM_BYTENUM[ram], sid = idd, name = name, type = svtype, handleFile = False)
                        srv.att = "Unverified: Server is created via unexsistent."
                        self.server_list.append(srv)

                    con.send(OutPacketGroup([]).data.data)
                    con.close()

                    crt = OutPacket(0xe2)
                    crt.writeByte(ram)
                    crt.writeString(idd)
                    crt.writeShort(port)
                    print(port)
                    if svtype == "verify":
                        c = 0x00
                        d = 0
                    crt.writeByte(c)
                    crt.writeShort(d)
                    self.bungee.queued.append(crt)
                    
                    
                    continue


                
                if typ == 0xa2:
                    ram = packet.readByte()
                    idd = packet.readString()
                    msg = packet.readString()
                    threading.Thread(target=lambda: tkmsg.showerror(f"[RS-{rsglobal.SERVER_RAM_BYTENUM[ram] + idd}] Broadcast System", datetime.datetime.now().strftime("%H:%M:%S") + f" An internal error occured on server [RS-{rsglobal.SERVER_RAM_BYTENUM[ram] + idd}]:\n\n" + msg)).start()
                    con.send(Status.OK)
                    con.close()
                    continue
                if typ == 0xa0:
                    ram = packet.readByte()
                    idd = packet.readString()
                    t = packet.readByte()
                    msg = packet.readString()

                    m = datetime.datetime.now().strftime("%H:%M:%S") + " " + msg
                    if t == 0:
                        func = tkmsg.showinfo
                    elif t == 1:
                        func = tkmsg.showwarning
                    elif t == 2:
                        func = tkmsg.showerror
                    threading.Thread(target=lambda: func(f"[RS-{rsglobal.SERVER_RAM_BYTENUM[ram] + idd}] Alert", m)).start()
                    con.send(OutPacketGroup([]).data.data)
                    con.close()
                    continue

                if typ == 0xa1:
                    ram = packet.readByte()
                    idd = packet.readString()
                    t = packet.readByte()
                    msg = packet.readString()

                    if t == 0:
                        l = "INFO"
                    elif t == 1:
                        l = "WARNING"
                    else:
                        l = "ERROR"
                    
                    for i in self.server_list:
                        if i.id == idd:
                            i.logs.append({"time": time.time(), "level": l, "msg": msg})
                            break

                    con.send(OutPacketGroup([]).data.data)
                    con.close()
                    continue

                if typ == 0xae:
                    ram = packet.readByte()
                    idd = packet.readString()
                    for i in self.server_list:
                        if i.id == idd:
                            i.status = "STOPPED"
                            self.server_list.remove(i)
                            break
                    con.send(OutPacketGroup([]).data.data)
                    con.close()

                    crt = OutPacket(0xe3)
                    crt.writeByte(ram)
                    crt.writeString(idd)
                    self.bungee.queued.append(crt)
                    
                    continue
                
                if typ == 0xf0:
                    ram = packet.readByte()
                    sid = packet.readString()
                    nam = packet.readString()
                    tps = float(packet.readString())
                    ramuse = packet.readLong()
                    players = packet.readTypeArray()
                    for i in self.server_list:
                        if i.id == sid:
                            i.name = nam
                            i.players = players     
                            i.ramused = ramuse
                            i.lastping = time.time()
                            i.tps = tps
                            break
                    else:
                        pack = OutPacket(0xc4)
                        pack.writeString("Server Not Found!")
                        con.send(OutPacketGroup([pack]).data.data)
                        con.close()
                        continue
                    group = OutPacketGroup(i.queued)
                    con.send(group.data.data)
                    con.close()
                    i.queued = []
                    continue

                if typ == 0xe9:
                    a = packet.readServerCode()
                    b = packet.readString()

                    c = packet.readServerCode()
                    d = packet.readString()

                    e = packet.readString()

                    crt = OutPacket(0xe9)
                    crt.writeString(c + d)
                    crt.writeString(e)
                    self.bungee.queued.append(crt)

                    con.send(OutPacketGroup([]).data.data)
                    con.close()
                    continue

                if typ == 0xe0:
                    playeramt = packet.readShort()
                    group = OutPacketGroup(self.bungee.queued)
                    con.send(group.data.data)
                    con.close()
                    self.bungee.queued = []
                    continue

                if typ == 0xe1:
                    threading.Thread(target=lambda: tkmsg.showinfo("[RS-BungeeCord] Alert", "BungeeCord is ready!")).start()
                    self.LOG.info("BungeeCord is ready!")
                    con.send(OutPacketGroup([]).data.data)
                    con.close()
                    continue

                if typ == 0xe2:

                    nam = packet.readString()
                    
                    al = []
                    for i in self.server_list:
                        al.append([i.fullId, len(i.players), i.maxplayers, i.type, i.name])
                    ot = OutPacket(0xe4)
                    ot.writeString(nam)
                    ot.writeShort(len(al))
                    for i in al:
                        ot.writeString(i[0])
                        ot.writeString(i[4])
                        ot.writeShort(i[1])
                        ot.writeShort(i[2])
                        ot.writeString(i[3])
                    con.send(OutPacketGroup([ot]).data.data)

                    print(OutPacketGroup([ot]).data.data)
                    con.close()
                    continue
            except Exception as e:
                n = traceback.format_exc()
                print("[Proxy] Packet " + str(data) + " issued an invalid request!")
                print(n)

            
                    

            con.send(OutPacketGroup([]).data.data)
            con.close()
            continue

