"""Android SDK EmulatorController hardware input, using the installed SDK wire contract."""

import configparser
import os
from pathlib import Path

import grpc
from google.protobuf import descriptor_pb2, descriptor_pool, empty_pb2, message_factory


class EmulatorHardware:
    def __init__(self, address="127.0.0.1:8554"):
        discovery = configparser.ConfigParser()
        discovery.read_string(
            "[emulator]\n" + Path(os.environ["EMULATOR_DISCOVERY_FILE"]).read_text(encoding="utf-8")
        )
        self.auth = (("authorization", "Bearer " + discovery["emulator"]["grpc.token"]),)
        # Field numbers/types are from SDK emulator/lib/emulator_controller.proto.
        # Enum fields use the identical int32 wire representation; only Evdev is used.
        file = descriptor_pb2.FileDescriptorProto(
            name="qa_emulator_input.proto", package="android.emulation.control", syntax="proto3"
        )
        for name, fields in {
            "KeyboardEvent": [(1, "codeType"), (2, "eventType"), (3, "keyCode")],
            "Touch": [(1, "x"), (2, "y"), (3, "identifier"), (4, "pressure")],
        }.items():
            message = file.message_type.add(name=name)
            for number, field_name in fields:
                message.field.add(name=field_name, number=number, type=5, label=1)
        message = file.message_type.add(name="TouchEvent")
        message.field.add(
            name="touches", number=1, type=11, type_name=".android.emulation.control.Touch", label=3
        )
        message.field.add(name="display", number=2, type=5, label=1)
        pool = descriptor_pool.DescriptorPool()
        pool.Add(file)
        self.keyboard = message_factory.GetMessageClass(
            pool.FindMessageTypeByName("android.emulation.control.KeyboardEvent")
        )
        self.touch_event = message_factory.GetMessageClass(
            pool.FindMessageTypeByName("android.emulation.control.TouchEvent")
        )
        self.channel = grpc.insecure_channel(address)
        grpc.channel_ready_future(self.channel).result(timeout=5)
        self.send_key = self.channel.unary_unary(
            "/android.emulation.control.EmulatorController/sendKey",
            request_serializer=lambda message: message.SerializeToString(),
            response_deserializer=empty_pb2.Empty.FromString,
        )
        self.send_touch = self.channel.unary_unary(
            "/android.emulation.control.EmulatorController/sendTouch",
            request_serializer=lambda message: message.SerializeToString(),
            response_deserializer=empty_pb2.Empty.FromString,
        )

    def key(self, code: int, down: bool):
        self.send_key(
            self.keyboard(codeType=1, eventType=0 if down else 1, keyCode=code),
            timeout=5,
            metadata=self.auth,
        )

    def touch(self, points: list[tuple[int, int, int, int]]):
        message = self.touch_event()
        for identifier, x, y, pressure in points:
            message.touches.add(identifier=identifier, x=x, y=y, pressure=pressure)
        self.send_touch(message, timeout=5, metadata=self.auth)
