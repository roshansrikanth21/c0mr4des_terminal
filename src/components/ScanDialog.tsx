import React, { useState, useRef } from 'react';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogTrigger
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Upload, ScanEye, Loader2, FileImage, CheckCircle, AlertCircle, Target, Send, Paperclip } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

interface AnalysisResult {
    patterns: string[];
    sentiment: string;
    confidence: number;
    recommendation: string;
    analysis: string;
}

export function ScanDialog() {
    const [isOpen, setIsOpen] = useState(false);
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [previewUrl, setPreviewUrl] = useState<string | null>(null);
    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const [result, setResult] = useState<AnalysisResult | null>(null);
    const [chatQuery, setChatQuery] = useState("");
    const [chatHistory, setChatHistory] = useState<{ role: 'user' | 'assistant', content: string, image?: string }[]>([]);
    const [isChatting, setIsChatting] = useState(false);
    const [chatImage, setChatImage] = useState<File | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const chatFileInputRef = useRef<HTMLInputElement>(null);

    const handleChatSubmit = async () => {
        if (!chatQuery.trim() && !chatImage || !result) return;

        const currentQuery = chatQuery;
        const currentImage = chatImage;

        setChatQuery("");
        setChatImage(null);
        setIsChatting(true);

        // Add user message to history immediately
        setChatHistory(prev => [
            ...prev,
            {
                role: 'user',
                content: currentQuery,
                image: currentImage ? URL.createObjectURL(currentImage) : undefined
            }
        ]);

        try {
            const formData = new FormData();
            formData.append('context', `Analysis: ${result.analysis}\nPatterns: ${result.patterns.join(', ')}\nRecommendation: ${result.recommendation}`);
            formData.append('question', currentQuery);

            if (currentImage) {
                formData.append('file', currentImage);
            }

            const res = await fetch('http://localhost:8000/api/chat_analysis', {
                method: 'POST',
                // Content-Type header is automatically set by browser for FormData
                body: formData
            });

            if (!res.ok) throw new Error("Chat failed");

            const data = await res.json();
            setChatHistory(prev => [...prev, { role: 'assistant', content: data.answer }]);
        } catch (err) {
            console.error(err);
            toast.error("Failed to get answer");
            setChatHistory(prev => [...prev, { role: 'assistant', content: "Error: Could not connect to analysis server." }]);
        } finally {
            setIsChatting(false);
        }
    };


    const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files && e.target.files[0]) {
            const file = e.target.files[0];
            setSelectedFile(file);
            setPreviewUrl(URL.createObjectURL(file));
            setResult(null); // Reset previous result
        }
    };

    const handleDragOver = (e: React.DragEvent) => {
        e.preventDefault();
    };

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            const file = e.dataTransfer.files[0];
            if (!file.type.startsWith('image/')) {
                toast.error("Please upload an image file");
                return;
            }
            setSelectedFile(file);
            setPreviewUrl(URL.createObjectURL(file));
            setResult(null);
        }
    };

    const handlePaste = async (e: React.ClipboardEvent) => {
        const items = e.clipboardData.items;
        for (const item of items) {
            if (item.type.indexOf('image') !== -1) {
                const file = item.getAsFile();
                if (file) {
                    setSelectedFile(file);
                    setPreviewUrl(URL.createObjectURL(file));
                    setResult(null);
                }
            }
        }
    };

    const handleAnalyze = async () => {
        if (!selectedFile) return;

        setIsAnalyzing(true);
        try {
            const formData = new FormData();
            formData.append('file', selectedFile);

            const res = await fetch('http://localhost:8000/api/analyze', {
                method: 'POST',
                body: formData,
            });

            if (!res.ok) throw new Error("Analysis failed");

            const data = await res.json();
            setResult(data);
            toast.success("Analysis Complete");
        } catch (err) {
            console.error(err);
            toast.error("Failed to analyze image");
        } finally {
            setIsAnalyzing(false);
        }
    };

    return (
        <Dialog open={isOpen} onOpenChange={setIsOpen}>
            <DialogTrigger asChild>
                <Button variant="outline" className="gap-2 border-primary/20 text-primary hover:bg-primary/10">
                    <ScanEye className="w-4 h-4" />
                    Scan Chart
                </Button>
            </DialogTrigger>
            <DialogContent className="sm:max-w-5xl h-[90vh] flex flex-col p-0 gap-0" onPaste={handlePaste}>
                <DialogHeader className="px-6 py-4 border-b border-border bg-background z-10">
                    <DialogTitle className="flex items-center gap-2">
                        <ScanEye className="w-5 h-5 text-primary" />
                        AI Chart Pattern Recognition
                    </DialogTitle>
                </DialogHeader>

                <div className="flex-1 overflow-hidden grid grid-cols-1 lg:grid-cols-2">
                    {/* LEFT COLUMN: Upload & Visuals */}
                    <div className="p-6 border-r border-border bg-secondary/10 flex flex-col gap-4 overflow-y-auto">
                        {/* Upload Area */}
                        <div
                            className={cn(
                                "border-2 border-dashed border-border rounded-lg flex flex-col items-center justify-center text-center cursor-pointer hover:bg-secondary/50 transition-colors relative transition-all duration-300",
                                previewUrl ? "h-64 border-primary/50" : "h-64"
                            )}
                            onClick={() => !previewUrl && fileInputRef.current?.click()}
                            onDragOver={handleDragOver}
                            onDrop={handleDrop}
                        >
                            <input
                                type="file"
                                ref={fileInputRef}
                                className="hidden"
                                accept="image/*"
                                onChange={handleFileSelect}
                            />

                            {previewUrl ? (
                                <div className="relative w-full h-full p-2">
                                    <img src={previewUrl} alt="Preview" className="w-full h-full object-contain rounded-md" />
                                    <Button
                                        size="sm"
                                        variant="destructive"
                                        className="absolute top-4 right-4 h-8 px-3 text-xs shadow-lg"
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            setSelectedFile(null);
                                            setPreviewUrl(null);
                                            setResult(null);
                                        }}
                                    >
                                        Remove Image
                                    </Button>
                                </div>
                            ) : (
                                <>
                                    <div className="w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center mb-4">
                                        <Upload className="w-8 h-8 text-primary" />
                                    </div>
                                    <p className="text-lg font-medium">Upload Chart Screenshot</p>
                                    <p className="text-sm text-muted-foreground mt-2">Drag & drop or Click to browse</p>
                                    <p className="text-xs text-muted-foreground mt-4 bg-secondary px-3 py-1 rounded-full">
                                        Tip: Paste (Ctrl+V) directly
                                    </p>
                                </>
                            )}
                        </div>

                        {/* Analyze Button */}
                        {selectedFile && !result && (
                            <Button size="lg" className="w-full gap-2 text-md py-6 shadow-lg shadow-primary/20" onClick={handleAnalyze} disabled={isAnalyzing}>
                                {isAnalyzing ? (
                                    <>
                                        <Loader2 className="w-5 h-5 animate-spin" />
                                        Analyzing Chart Patterns...
                                    </>
                                ) : (
                                    <>
                                        <ScanEye className="w-5 h-5" />
                                        Run AI Analysis
                                    </>
                                )}
                            </Button>
                        )}

                        {/* Trade Signal Box (The "Side Box" Request) */}
                        {result && (
                            <div className="mt-4 p-4 rounded-xl border border-border bg-card shadow-sm space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-500 delay-100">
                                <div className="flex items-center justify-between pb-2 border-b border-border/50">
                                    <h3 className="font-mono text-sm font-bold uppercase text-muted-foreground">Trade Intelligence</h3>
                                    <Badge variant={result.sentiment === 'Bullish' ? 'default' : 'destructive'}>
                                        {result.sentiment}
                                    </Badge>
                                </div>

                                <div className="grid grid-cols-2 gap-3">
                                    <div className="p-3 bg-secondary/50 rounded-lg">
                                        <span className="text-[10px] uppercase text-muted-foreground font-bold">Action</span>
                                        <div className="text-lg font-bold text-primary mt-1">{result.recommendation.split(' ')[0]}</div>
                                    </div>
                                    <div className="p-3 bg-secondary/50 rounded-lg">
                                        <span className="text-[10px] uppercase text-muted-foreground font-bold">Confidence</span>
                                        <div className="text-lg font-bold mt-1">{(result.confidence * 100).toFixed(0)}%</div>
                                    </div>
                                </div>

                                <div className="space-y-2">
                                    <div className="flex items-center justify-between text-sm p-2 rounded bg-green-500/10 border border-green-500/20 text-green-700 dark:text-green-300">
                                        <span className="font-semibold flex items-center gap-2"><Target className="w-3 h-3" /> Target</span>
                                        <span className="font-mono">See Analysis</span>
                                    </div>
                                    <div className="flex items-center justify-between text-sm p-2 rounded bg-red-500/10 border border-red-500/20 text-red-700 dark:text-red-300">
                                        <span className="font-semibold flex items-center gap-2"><AlertCircle className="w-3 h-3" /> Stop Loss</span>
                                        <span className="font-mono">See Analysis</span>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* RIGHT COLUMN: Analysis & Chat */}
                    <div className="flex flex-col h-full overflow-hidden bg-card">
                        {result ? (
                            <>
                                {/* Scrollable Analysis Text */}
                                <div className="flex-1 overflow-y-auto p-6 space-y-6">
                                    <div>
                                        <h3 className="text-sm font-bold uppercase text-muted-foreground mb-3 flex items-center gap-2">
                                            <FileImage className="w-4 h-4" /> Comprehensive Analysis
                                        </h3>
                                        <div className="prose prose-sm dark:prose-invert max-w-none text-foreground/90 leading-relaxed p-4 bg-secondary/20 rounded-lg border border-border/50">
                                            {result.analysis}
                                        </div>
                                    </div>

                                    <div>
                                        <h3 className="text-sm font-bold uppercase text-muted-foreground mb-3">Detected Patterns</h3>
                                        <div className="flex flex-wrap gap-2">
                                            {result.patterns.map((p, i) => (
                                                <Badge key={i} variant="outline" className="px-3 py-1 flex items-center gap-1.5 text-xs">
                                                    <CheckCircle className="w-3 h-3 text-primary" />
                                                    {p}
                                                </Badge>
                                            ))}
                                        </div>
                                    </div>

                                    {/* Chat History */}
                                    {chatHistory.length > 0 && (
                                        <div className="border-t border-border pt-6">
                                            <h3 className="text-sm font-bold uppercase text-muted-foreground mb-3">Q&A History</h3>
                                            <div className="space-y-4">
                                                {chatHistory.map((msg, i) => (
                                                    <div key={i} className={cn("p-3 rounded-lg text-sm", msg.role === 'user' ? "bg-primary/10 ml-8" : "bg-secondary/30 mr-8")}>
                                                        <span className="font-bold block text-[10px] uppercase opacity-50 mb-1">{msg.role === 'user' ? 'You' : 'AI Analyst'}</span>
                                                        {msg.image && (
                                                            <div className="mb-2">
                                                                <img src={msg.image} alt="Attached context" className="h-20 rounded border border-border/50" />
                                                            </div>
                                                        )}
                                                        {msg.content}
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>

                                {/* Chat Interface Input */}
                                <div className="p-4 border-t border-border bg-secondary/10">
                                    <form
                                        className="flex gap-2 items-end"
                                        onSubmit={(e) => {
                                            e.preventDefault();
                                            handleChatSubmit();
                                        }}
                                    >
                                        <div className="flex-1 flex flex-col gap-2">
                                            {/* Image Preview if selected */}
                                            {chatImage && (
                                                <div className="relative inline-block w-fit">
                                                    <img src={URL.createObjectURL(chatImage)} alt="Preview" className="h-16 rounded border border-border" />
                                                    <button
                                                        type="button"
                                                        onClick={() => setChatImage(null)}
                                                        className="absolute -top-2 -right-2 bg-destructive text-destructive-foreground rounded-full w-5 h-5 flex items-center justify-center text-xs"
                                                    >
                                                        ×
                                                    </button>
                                                </div>
                                            )}

                                            <div className="flex gap-2">
                                                {/* Hidden File Input */}
                                                <input
                                                    type="file"
                                                    ref={chatFileInputRef}
                                                    className="hidden"
                                                    accept="image/*"
                                                    onChange={(e) => {
                                                        if (e.target.files?.[0]) setChatImage(e.target.files[0]);
                                                    }}
                                                />

                                                {/* Attach Button */}
                                                <Button
                                                    type="button"
                                                    size="icon"
                                                    variant="outline"
                                                    className="shrink-0"
                                                    onClick={() => chatFileInputRef.current?.click()}
                                                    title="Attach Image"
                                                >
                                                    <Paperclip className="w-4 h-4" />
                                                </Button>

                                                <input
                                                    className="flex-1 bg-background border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                                                    placeholder="Ask a follow-up question..."
                                                    value={chatQuery}
                                                    onChange={(e) => setChatQuery(e.target.value)}
                                                    disabled={isChatting}
                                                />
                                            </div>
                                        </div>

                                        <Button size="sm" type="submit" disabled={isChatting || (!chatQuery.trim() && !chatImage)}>
                                            {isChatting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                                        </Button>
                                    </form>
                                    <p className="text-[10px] text-muted-foreground mt-2 text-center">AI can answer questions based on the chart analysis above.</p>
                                </div>
                            </>
                        ) : (
                            <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground p-10 text-center">
                                <ScanEye className="w-12 h-12 mb-4 opacity-20" />
                                <p>Upload a chart to view detailed analysis and trade setups here.</p>
                            </div>
                        )}
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    );
}
